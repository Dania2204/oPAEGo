from django.db import models

from apps.catalogo.models import LATITUD, LONGITUD, Conductor
from apps.envios.models import _coordenada


class PosicionEnVivo(models.Model):
    """Última posición del conductor mientras tiene la sesión abierta.

    Modo de prueba del mapa en vivo: es independiente de los envíos (RF-21
    sigue registrando la ruta de cada envío en `envios.Ubicacion`).
    """

    conductor = models.OneToOneField(
        Conductor, on_delete=models.CASCADE, related_name="posicion_en_vivo"
    )
    latitud = _coordenada(LATITUD)
    longitud = _coordenada(LONGITUD)
    precision_m = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    velocidad_kmh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rumbo = models.PositiveSmallIntegerField(null=True, blank=True)
    en_linea = models.BooleanField(default=True)
    actualizado_en = models.DateTimeField()

    class Meta:
        verbose_name = "posición en vivo"
        verbose_name_plural = "posiciones en vivo"

    def __str__(self):
        return f"{self.conductor} @ {self.latitud}, {self.longitud}"
