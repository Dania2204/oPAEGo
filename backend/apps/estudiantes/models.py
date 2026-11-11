"""Estudiantes que reciben el PAE y su entrega diaria.

Protección de datos (Ley 1581, art. 5-7): son datos de menores y la plantilla facial
es un dato sensible. Por eso:
- Del Anexo 6A de SIMAT solo se guarda la identidad mínima (documento, nombre y
  curso). Dirección, teléfono, SISBÉN, víctima, discapacidad, etnia, fecha de
  nacimiento, etc. nunca entran a la base de datos.
- Las plantillas faciales solo existen con una autorización vigente del acudiente,
  se guardan cifradas (`cifrado.py`), nunca se guardan fotos y se borran al revocar
  la autorización o dar de baja al estudiante.
- La entrega siempre se puede registrar sin biometría (método MANUAL): la cara no
  es el único mecanismo.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalogo.models import Institucion
from apps.catalogo.simat import etiqueta_grado

from . import cifrado


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
    def autorizacion_vigente(self):
        autorizacion = getattr(self, "autorizacion", None)
        return autorizacion if autorizacion and autorizacion.vigente else None


class AutorizacionBiometrica(models.Model):
    """Autorización previa, expresa e informada del acudiente (Ley 1581, art. 7)."""

    estudiante = models.OneToOneField(
        Estudiante, on_delete=models.PROTECT, related_name="autorizacion"
    )
    acudiente_nombre = models.CharField(max_length=150)
    acudiente_documento = models.CharField(max_length=20)
    parentesco = models.CharField(max_length=50)
    otorgada_en = models.DateTimeField()
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    revocada_en = models.DateTimeField(null=True, blank=True)
    revocada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "autorización biométrica"
        verbose_name_plural = "autorizaciones biométricas"

    def __str__(self):
        estado = "vigente" if self.vigente else "revocada"
        return f"{self.estudiante} — {estado}"

    @property
    def vigente(self):
        return self.revocada_en is None


class PlantillaFacial(models.Model):
    """Vector de la cara (no una foto), cifrado con BIOMETRIA_CLAVE."""

    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name="plantillas")
    vector_cifrado = models.TextField(editable=False)
    dimension = models.PositiveSmallIntegerField()
    modelo = models.CharField(max_length=40, help_text="Modelo que generó el vector.")
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "plantilla facial"
        verbose_name_plural = "plantillas faciales"
        ordering = ["estudiante", "id"]

    def __str__(self):
        return f"Plantilla de {self.estudiante} ({self.modelo})"

    @property
    def vector(self):
        return cifrado.descifrar_vector(self.vector_cifrado)

    @vector.setter
    def vector(self, valores):
        self.vector_cifrado = cifrado.cifrar_vector(valores)
        self.dimension = len(valores)


class EntregaInmutableError(Exception):
    """Una entrega registrada no se modifica ni se borra (trazabilidad del PAE)."""


class _EntregaQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise EntregaInmutableError("Una entrega registrada no se puede modificar.")

    def delete(self):
        raise EntregaInmutableError("Una entrega registrada no se puede eliminar.")


class MetodoEntrega(models.TextChoices):
    FACIAL = "FACIAL", "Reconocimiento facial"
    MANUAL = "MANUAL", "Registro manual"


class EntregaEstudiante(models.Model):
    """El estudiante recibió el PAE ese día (una sola vez por día)."""

    estudiante = models.ForeignKey(Estudiante, on_delete=models.PROTECT, related_name="entregas")
    fecha = models.DateField(db_index=True)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas_pae"
    )
    metodo = models.CharField(max_length=10, choices=MetodoEntrega.choices)
    motivo = models.TextField(
        blank=True, help_text="Obligatorio en el registro manual (por qué sin cámara)."
    )
    similitud = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
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
