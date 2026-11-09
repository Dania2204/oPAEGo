from django.conf import settings
from django.db import models


class OperacionCliente(models.Model):
    """RF-38 / RNF-21: operación capturada en un dispositivo (posiblemente sin
    conexión). El `uuid_cliente` lo genera el dispositivo; si la misma
    operación llega dos veces se devuelve el resultado guardado (idempotencia).
    """

    class Resultado(models.TextChoices):
        OK = "ok", "Aplicada"
        RECHAZADA = "rechazado", "Rechazada"

    uuid_cliente = models.UUIDField(unique=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="operaciones_cliente"
    )
    tipo = models.CharField(max_length=40)
    ocurrido_en = models.DateTimeField()
    recibido_en = models.DateTimeField(auto_now_add=True)
    resultado = models.CharField(max_length=10, choices=Resultado.choices)
    respuesta = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "operación sincronizada"
        verbose_name_plural = "operaciones sincronizadas"
        ordering = ["-recibido_en"]

    def __str__(self):
        return f"{self.tipo} {self.uuid_cliente} ({self.resultado})"
