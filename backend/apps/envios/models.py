import hashlib
import json
import secrets
from datetime import UTC
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.catalogo.models import LATITUD, LONGITUD, Conductor, Institucion, Vehiculo

from .estados import ESTADOS_ENTREGADOS, Estado


def _coordenada(validadores, **kwargs):
    return models.DecimalField(max_digits=9, decimal_places=6, validators=validadores, **kwargs)


def generar_codigo_verificacion():
    return f"{secrets.randbelow(1_000_000):06d}"


class Envio(models.Model):
    """RF-13 a RF-18: envío de alimentos de la entidad a una institución."""

    codigo = models.CharField(max_length=20, unique=True, editable=False)
    programado_para = models.DateTimeField("fecha y hora programadas", db_index=True)
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name="envios")
    conductor = models.ForeignKey(Conductor, on_delete=models.PROTECT, related_name="envios")
    vehiculo = models.ForeignKey(
        Vehiculo, null=True, blank=True, on_delete=models.PROTECT, related_name="envios"
    )
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.ASIGNADO)
    observaciones = models.TextField(blank=True)
    # RF-27: código que el conductor muestra y la institución digita al recibir.
    codigo_verificacion = models.CharField(
        max_length=6, default=generar_codigo_verificacion, editable=False
    )

    salida_en = models.DateTimeField(null=True, blank=True)
    salida_latitud = _coordenada(LATITUD, null=True, blank=True)
    salida_longitud = _coordenada(LONGITUD, null=True, blank=True)
    llegada_en = models.DateTimeField(null=True, blank=True)
    llegada_latitud = _coordenada(LATITUD, null=True, blank=True)
    llegada_longitud = _coordenada(LONGITUD, null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)
    cancelado_en = models.DateTimeField(null=True, blank=True)
    motivo_cancelacion = models.TextField(blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="envios_creados"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "envío"
        ordering = ["-programado_para"]
        indexes = [models.Index(fields=["estado", "programado_para"])]

    def __str__(self):
        return self.codigo

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = self._nuevo_codigo()
        super().save(*args, **kwargs)

    def _nuevo_codigo(self):
        fecha = timezone.localtime(self.programado_para or timezone.now()).strftime("%y%m%d")
        while True:
            codigo = f"PAE-{fecha}-{secrets.token_hex(2).upper()}"
            if not Envio.objects.filter(codigo=codigo).exists():
                return codigo

    @property
    def fue_entregado(self):
        return self.estado in ESTADOS_ENTREGADOS

    @property
    def limite_entrega(self):
        from datetime import timedelta

        return self.programado_para + timedelta(minutes=settings.PAEGO["TOLERANCIA_ENTREGA_MIN"])

    @property
    def entregado_a_tiempo(self):
        if not self.fue_entregado or not self.entregado_en:
            return None
        return self.entregado_en <= self.limite_entrega

    @property
    def esta_retrasado(self):
        """RF-30: superó la hora programada (más tolerancia) sin entregarse."""
        return self.estado in (Estado.ASIGNADO, Estado.EN_TRANSITO) and (
            timezone.now() > self.limite_entrega
        )

    @property
    def tiene_registro_completo(self):
        """Indicador de trazabilidad (Tabla 3): fecha, hora, responsable,
        ubicación y evidencia."""
        evidencia = getattr(self, "evidencia", None)
        return bool(
            self.salida_en
            and self.salida_latitud is not None
            and self.llegada_en
            and self.llegada_latitud is not None
            and evidencia is not None
            and evidencia.recibido_por_nombre
            and evidencia.latitud is not None
        )


class ItemEnvio(models.Model):
    """RF-14: detalle de alimentos programados; RF-25: cantidad recibida."""

    class Unidad(models.TextChoices):
        UNIDAD = "UNIDAD", "Unidades"
        RACION = "RACION", "Raciones"
        KG = "KG", "Kilogramos"
        G = "G", "Gramos"
        L = "L", "Litros"
        CAJA = "CAJA", "Cajas"
        PAQUETE = "PAQUETE", "Paquetes"
        BULTO = "BULTO", "Bultos"

    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name="items")
    producto = models.CharField(max_length=150)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    unidad = models.CharField(max_length=10, choices=Unidad.choices)
    cantidad_recibida = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "ítem del envío"
        verbose_name_plural = "ítems del envío"
        ordering = ["id"]

    def __str__(self):
        return f"{self.producto}: {self.cantidad} {self.get_unidad_display()}"

    @property
    def diferencia(self):
        if self.cantidad_recibida is None:
            return None
        return self.cantidad_recibida - self.cantidad


class Ubicacion(models.Model):
    """RF-21 / RF-35: posición transmitida periódicamente por el conductor."""

    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name="ubicaciones")
    conductor = models.ForeignKey(Conductor, on_delete=models.PROTECT, related_name="ubicaciones")
    latitud = _coordenada(LATITUD)
    longitud = _coordenada(LONGITUD)
    precision_m = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    velocidad_kmh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rumbo = models.PositiveSmallIntegerField(null=True, blank=True)
    ocurrido_en = models.DateTimeField()
    recibido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ubicación"
        verbose_name_plural = "ubicaciones"
        ordering = ["ocurrido_en"]
        indexes = [models.Index(fields=["envio", "ocurrido_en"])]

    def __str__(self):
        return f"{self.envio} @ {self.latitud}, {self.longitud}"


class Novedad(models.Model):
    """RF-23 / RF-28: novedad reportada en el trayecto o en la recepción."""

    class Tipo(models.TextChoices):
        RETRASO = "RETRASO", "Retraso"
        DANO = "DANO", "Daño"
        FALTANTE = "FALTANTE", "Faltante"
        INCIDENTE = "INCIDENTE", "Incidente"
        ENTREGA_INCOMPLETA = "ENTREGA_INCOMPLETA", "Entrega incompleta"

    class Origen(models.TextChoices):
        TRAYECTO = "TRAYECTO", "Trayecto (conductor)"
        RECEPCION = "RECEPCION", "Recepción (institución)"
        ADMINISTRACION = "ADMINISTRACION", "Administración"

    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name="novedades")
    reportado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="novedades_reportadas"
    )
    origen = models.CharField(max_length=15, choices=Origen.choices)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.TextField()
    foto = models.ImageField(upload_to="novedades/%Y/%m/", null=True, blank=True)
    latitud = _coordenada(LATITUD, null=True, blank=True)
    longitud = _coordenada(LONGITUD, null=True, blank=True)
    ocurrido_en = models.DateTimeField()
    recibido_en = models.DateTimeField(auto_now_add=True)
    # RF-31: notificación al administrador.
    leida_en = models.DateTimeField(null=True, blank=True)
    leida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="novedades_leidas",
    )

    class Meta:
        verbose_name_plural = "novedades"
        ordering = ["-ocurrido_en"]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.envio}"

    @property
    def diferida(self):
        """RF-38: se registró sin conexión y llegó al servidor después."""
        from datetime import timedelta

        umbral = timedelta(minutes=settings.PAEGO["UMBRAL_DIFERIDO_MIN"])
        return bool(self.recibido_en and self.recibido_en - self.ocurrido_en > umbral)


class EvidenciaEntrega(models.Model):
    """RF-27 / RNF-20: evidencia electrónica con autenticidad e integridad
    (Ley 527 de 1999) mediante código de verificación y huella SHA-256."""

    envio = models.OneToOneField(Envio, on_delete=models.CASCADE, related_name="evidencia")
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evidencias"
    )
    recibido_por_nombre = models.CharField("recibido por", max_length=150)
    recibido_por_cargo = models.CharField(max_length=100, blank=True)
    codigo_verificacion = models.CharField(max_length=6)
    foto = models.ImageField(upload_to="evidencias/%Y/%m/", null=True, blank=True)
    foto_sha256 = models.CharField(max_length=64, blank=True)
    latitud = _coordenada(LATITUD, null=True, blank=True)
    longitud = _coordenada(LONGITUD, null=True, blank=True)
    ocurrido_en = models.DateTimeField()
    recibido_en = models.DateTimeField(auto_now_add=True)
    huella_sha256 = models.CharField(max_length=64, editable=False)

    class Meta:
        verbose_name = "evidencia de entrega"
        verbose_name_plural = "evidencias de entrega"

    def __str__(self):
        return f"Evidencia de {self.envio}"

    def contenido_canonico(self):
        """Representación estable: el mismo valor antes y después de guardar
        (decimales con escala fija y fecha en UTC)."""

        def decimal(valor, cifras):
            return None if valor is None else format(Decimal(str(valor)), f".{cifras}f")

        items = [
            {
                "producto": i.producto,
                "programado": decimal(i.cantidad, 2),
                "recibido": decimal(i.cantidad_recibida, 2),
                "unidad": i.unidad,
            }
            for i in self.envio.items.order_by("id")
        ]
        contenido = {
            "envio": self.envio.codigo,
            "institucion_id": self.envio.institucion_id,
            "conductor_id": self.envio.conductor_id,
            "registrado_por_id": self.registrado_por_id,
            "recibido_por_nombre": self.recibido_por_nombre,
            "recibido_por_cargo": self.recibido_por_cargo,
            "codigo_verificacion": self.codigo_verificacion,
            "foto_sha256": self.foto_sha256,
            "latitud": decimal(self.latitud, 6),
            "longitud": decimal(self.longitud, 6),
            "ocurrido_en": self.ocurrido_en.astimezone(UTC).isoformat(),
            "items": items,
        }
        return json.dumps(contenido, sort_keys=True, ensure_ascii=False)

    def calcular_huella(self):
        return hashlib.sha256(self.contenido_canonico().encode("utf-8")).hexdigest()

    @property
    def es_integra(self):
        """True si la evidencia no ha sido alterada desde que se registró."""
        return (
            self.codigo_verificacion == self.envio.codigo_verificacion
            and self.huella_sha256 == self.calcular_huella()
        )
