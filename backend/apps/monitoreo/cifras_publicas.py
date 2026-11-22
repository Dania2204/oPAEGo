"""Cifras agregadas para la página pública (landing).

Solo conteos: ningún dato personal ni de una institución en particular. Se
guardan en la caché unos minutos porque la landing es pública y no debe pegarle
a la base en cada visita.
"""

from functools import cache as memorizar
from types import SimpleNamespace

from django.core.cache import cache
from django.utils.safestring import mark_safe

from apps.catalogo.models import Institucion
from apps.envios.models import Envio
from apps.estudiantes import qr
from apps.estudiantes.models import EntregaEstudiante, Estudiante

CLAVE = "paego:cifras-publicas"
DURACION_SEG = 10 * 60


def cifras():
    datos = cache.get(CLAVE)
    if datos is None:
        datos = {
            "instituciones": Institucion.objects.filter(activo=True).count(),
            "estudiantes": Estudiante.objects.filter(activo=True).count(),
            "envios": Envio.objects.count(),
            "entregas": EntregaEstudiante.objects.count(),
        }
        cache.set(CLAVE, datos, DURACION_SEG)
    return datos


@memorizar
def qr_de_ejemplo():
    """QR de la maqueta del teléfono. No es de ningún estudiante: la app lo rechaza
    porque no lleva el prefijo `PAEGO-E1:`."""
    ejemplo = SimpleNamespace(contenido_qr="PAEGO-DEMO", nombre_completo="un estudiante de ejemplo")
    return mark_safe(qr.svg(ejemplo, margen=2))  # noqa: S308 (SVG generado aquí, sin datos externos)
