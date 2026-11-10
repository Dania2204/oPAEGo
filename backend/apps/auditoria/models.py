from django.conf import settings
from django.db import models


class RegistroInmutableError(Exception):
    """RNF-12: el registro de auditoría no se puede modificar ni eliminar."""


class _RegistroQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise RegistroInmutableError("El registro de auditoría no se puede modificar.")

    def delete(self):
        raise RegistroInmutableError("El registro de auditoría no se puede eliminar.")


class Accion(models.TextChoices):
    INICIO_SESION = "INICIO_SESION", "Inicio de sesión"
    CIERRE_SESION = "CIERRE_SESION", "Cierre de sesión"
    RESTABLECER_CONTRASENA = "RESTABLECER_CONTRASENA", "Restablecimiento de contraseña"
    ACEPTA_TRATAMIENTO_DATOS = "ACEPTA_TRATAMIENTO_DATOS", "Aceptación de tratamiento de datos"
    CREAR = "CREAR", "Creación"
    EDITAR = "EDITAR", "Edición"
    DESACTIVAR = "DESACTIVAR", "Desactivación"
    ACTIVAR = "ACTIVAR", "Activación"
    ENVIO_CREADO = "ENVIO_CREADO", "Envío creado y asignado"
    ENVIO_EDITADO = "ENVIO_EDITADO", "Envío modificado"
    ENVIO_REASIGNADO = "ENVIO_REASIGNADO", "Envío reasignado"
    ENVIO_CANCELADO = "ENVIO_CANCELADO", "Envío cancelado"
    SALIDA = "SALIDA", "Salida del vehículo"
    LLEGADA = "LLEGADA", "Llegada a la institución"
    NOVEDAD = "NOVEDAD", "Novedad reportada"
    RECEPCION_CONFIRMADA = "RECEPCION_CONFIRMADA", "Recepción confirmada"
    RECEPCION_CON_NOVEDAD = "RECEPCION_CON_NOVEDAD", "Recepción con novedad"
    CIERRE_CON_NOVEDAD = "CIERRE_CON_NOVEDAD", "Envío cerrado con novedad"
    SINCRONIZACION_RECHAZADA = "SINCRONIZACION_RECHAZADA", "Operación sin conexión rechazada"
    EXPORTAR_REPORTE = "EXPORTAR_REPORTE", "Exportación de reporte"
    AUTORIZACION_BIOMETRICA = "AUTORIZACION_BIOMETRICA", "Autorización biométrica registrada"
    AUTORIZACION_REVOCADA = "AUTORIZACION_REVOCADA", "Autorización biométrica revocada"
    ROSTRO_INSCRITO = "ROSTRO_INSCRITO", "Rostro de estudiante inscrito"
    ROSTRO_BORRADO = "ROSTRO_BORRADO", "Plantillas faciales borradas"
    ENTREGA_ESTUDIANTE = "ENTREGA_ESTUDIANTE", "Entrega del PAE a estudiante"


class RegistroAuditoria(models.Model):
    """RF-33: cada acción relevante con usuario, fecha, hora y ubicación."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registros_auditoria",
    )
    accion = models.CharField(max_length=40, choices=Accion.choices)
    entidad = models.CharField(max_length=40, blank=True)
    entidad_id = models.CharField(max_length=40, blank=True)
    envio = models.ForeignKey(
        "envios.Envio",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registros_auditoria",
    )
    descripcion = models.TextField(blank=True)
    datos = models.JSONField(default=dict, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # RF-38: hora real del evento (puede venir de un dispositivo sin conexión)
    # y hora en que el servidor lo recibió.
    ocurrido_en = models.DateTimeField(db_index=True)
    registrado_en = models.DateTimeField(auto_now_add=True)
    diferido = models.BooleanField(
        default=False, help_text="Se registró sin conexión y se sincronizó después."
    )
    ip = models.GenericIPAddressField(null=True, blank=True)

    objects = _RegistroQuerySet.as_manager()

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-ocurrido_en", "-id"]
        indexes = [models.Index(fields=["envio", "ocurrido_en"])]

    def __str__(self):
        return f"{self.get_accion_display()} — {self.ocurrido_en:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RegistroInmutableError("El registro de auditoría no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroInmutableError("El registro de auditoría no se puede eliminar.")
