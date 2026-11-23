from django.conf import settings
from django.db import models


class ConversacionAsistente(models.Model):
    """Conversación del administrador con el asistente de reportes.

    `mensajes` guarda la conversación tal como la devolvió la API de Anthropic
    (incluidos los bloques de razonamiento, que deben reenviarse sin cambios).
    `turnos` es lo que se muestra: pregunta, respuesta y qué datos se consultaron.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversaciones_ia"
    )
    titulo = models.CharField(max_length=120)
    mensajes = models.JSONField(default=list)
    turnos = models.JSONField(default=list)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizado_en"]
        verbose_name = "conversación con el asistente"
        verbose_name_plural = "conversaciones con el asistente"

    def __str__(self):
        return self.titulo
