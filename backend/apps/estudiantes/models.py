"""Estudiantes que reciben el PAE y su entrega diaria.

Protección de datos (Ley 1581, art. 5-7): son datos de menores. Por eso:
- Del Anexo 6A de SIMAT solo se guarda la identidad mínima (documento, nombre y
  curso). Dirección, teléfono, SISBÉN, víctima, discapacidad, etnia, fecha de
  nacimiento, etc. nunca entran a la base de datos.
- Cada estudiante se identifica con un código QR propio (`codigo_qr`): un token
  aleatorio que no contiene datos personales. Si el carné se pierde, el código se
  regenera y el anterior deja de servir.
- La entrega siempre se puede registrar sin el carné (método MANUAL, con motivo).
"""

import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalogo.models import Institucion
from apps.catalogo.simat import etiqueta_documento, etiqueta_grado

# Prefijo versionado: la app rechaza cualquier QR que no sea de PAEGo.
PREFIJO_QR = "PAEGO-E1:"


def nuevo_codigo_qr():
    """Token aleatorio de 22 caracteres (128 bits): imposible de adivinar."""
    return secrets.token_urlsafe(16)


class Supervisor(models.Model):
    """Usuario con rol SUPERVISOR y la institución en la que registra entregas."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="supervisor"
    )
    institucion = models.ForeignKey(
        Institucion, on_delete=models.PROTECT, related_name="supervisores"
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "supervisor PAE"
        verbose_name_plural = "supervisores PAE"
        ordering = ["institucion__nombre", "usuario__first_name"]

    def __str__(self):
        return f"{self.usuario.get_full_name()} — {self.institucion}"


class Estudiante(models.Model):
    institucion = models.ForeignKey(
        Institucion, on_delete=models.PROTECT, related_name="estudiantes"
    )
    # PER_ID de SIMAT: identificador estable del estudiante entre cortes de matrícula.
    simat_per_id = models.CharField("PER_ID de SIMAT", max_length=20, unique=True)
    tipo_documento = models.CharField(max_length=10)
    numero_documento = models.CharField(max_length=20, db_index=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    grado = models.CharField(max_length=4)  # código SIMAT; etiqueta en catalogo.simat
    grupo = models.CharField(max_length=10, blank=True)
    jornada = models.CharField(max_length=2, blank=True)
    sede_simat = models.CharField("consecutivo de sede (SIMAT)", max_length=20, blank=True)
    codigo_qr = models.CharField(
        "código QR", max_length=32, unique=True, default=nuevo_codigo_qr, editable=False
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["institucion__nombre", "grado", "grupo", "apellidos", "nombres"]
        indexes = [models.Index(fields=["institucion", "grado", "grupo"])]

    def __str__(self):
        return f"{self.nombre_completo} ({self.curso})"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def curso(self):
        grado = etiqueta_grado(self.grado)
        return f"{grado} {self.grupo}".strip()

    @property
    def tipo_documento_etiqueta(self):
        return etiqueta_documento(self.tipo_documento)

    @property
    def documento(self):
        return f"{self.tipo_documento_etiqueta} {self.numero_documento}".strip()

    @property
    def contenido_qr(self):
        """Texto que lleva el QR impreso; la app lo escanea."""
        return f"{PREFIJO_QR}{self.codigo_qr}"


class EntregaInmutableError(Exception):
    """Una entrega registrada no se modifica ni se borra (trazabilidad del PAE)."""


class _EntregaQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise EntregaInmutableError("Una entrega registrada no se puede modificar.")

    def delete(self):
        raise EntregaInmutableError("Una entrega registrada no se puede eliminar.")


class MetodoEntrega(models.TextChoices):
    QR = "QR", "Código QR"
    MANUAL = "MANUAL", "Registro manual"
    # Histórico: entregas registradas antes del cambio a QR (son inmutables).
    FACIAL = "FACIAL", "Reconocimiento facial"


class EntregaEstudiante(models.Model):
    """El estudiante recibió el PAE ese día (una sola vez por día)."""

    estudiante = models.ForeignKey(Estudiante, on_delete=models.PROTECT, related_name="entregas")
    fecha = models.DateField(db_index=True)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas_pae"
    )
    metodo = models.CharField(max_length=10, choices=MetodoEntrega.choices)
    motivo = models.TextField(
        blank=True, help_text="Obligatorio en el registro manual (por qué sin el código QR)."
    )
    ocurrido_en = models.DateTimeField()
    registrado_en = models.DateTimeField(auto_now_add=True)
    diferido = models.BooleanField(default=False)

    objects = _EntregaQuerySet.as_manager()

    class Meta:
        verbose_name = "entrega a estudiante"
        verbose_name_plural = "entregas a estudiantes"
        ordering = ["-fecha", "estudiante__grado", "estudiante__grupo", "estudiante__apellidos"]
        constraints = [
            models.UniqueConstraint(fields=["estudiante", "fecha"], name="una_entrega_por_dia"),
            models.CheckConstraint(
                condition=~Q(metodo=MetodoEntrega.MANUAL) | ~Q(motivo=""),
                name="entrega_manual_con_motivo",
            ),
        ]

    def __str__(self):
        return f"{self.estudiante} — {self.fecha:%Y-%m-%d} ({self.get_metodo_display()})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise EntregaInmutableError("Una entrega registrada no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise EntregaInmutableError("Una entrega registrada no se puede eliminar.")


# Estudiantes agregados a mano (llegan a mitad de año, antes del siguiente corte de
# SIMAT) llevan este prefijo en lugar del PER_ID. Cuando el Anexo 6A los trae, la
# importación los reconoce por su documento y les pone el PER_ID real (conservan
# su QR y sus entregas).
PREFIJO_MANUAL = "MANUAL-"


def nuevo_per_id_manual():
    return f"{PREFIJO_MANUAL}{secrets.token_hex(6)}"


class EstadoImportacion(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente de confirmar"
    APLICADA = "APLICADA", "Aplicada"
    DESCARTADA = "DESCARTADA", "Descartada"


class ImportacionEstudiantes(models.Model):
    """Actualización de la matrícula de una institución desde el Anexo 6A.

    Se hace en dos pasos: al subir el archivo se lee y se muestra qué va a
    cambiar (nuevos, cambios de curso, retirados); al confirmar se aplica. Entre
    un paso y otro las filas leídas (solo identidad mínima) quedan en `filas`;
    al aplicar o descartar se borran y solo queda el resumen (Ley 1581).
    """

    institucion = models.ForeignKey(
        Institucion, on_delete=models.PROTECT, related_name="importaciones_estudiantes"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    nombre_archivo = models.CharField(max_length=200)
    codigo_dane = models.CharField(max_length=20)
    estado = models.CharField(
        max_length=10, choices=EstadoImportacion.choices, default=EstadoImportacion.PENDIENTE
    )
    filas = models.JSONField(default=dict, blank=True)
    resumen = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    aplicado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "importación de estudiantes"
        verbose_name_plural = "importaciones de estudiantes"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.institucion} — {self.nombre_archivo} ({self.get_estado_display()})"
