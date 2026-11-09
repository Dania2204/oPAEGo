"""Estados del envío y transiciones permitidas por rol (RF-18).

Los estados son exactamente los del documento: asignado, en tránsito,
entregado, con novedad y cancelado. El envío nace en ASIGNADO porque se crea
con su conductor (RF-13 + RF-15).
"""

from django.db import models

from apps.cuentas.models import Rol


class Estado(models.TextChoices):
    ASIGNADO = "ASIGNADO", "Asignado"
    EN_TRANSITO = "EN_TRANSITO", "En tránsito"
    ENTREGADO = "ENTREGADO", "Entregado"
    CON_NOVEDAD = "CON_NOVEDAD", "Con novedad"
    CANCELADO = "CANCELADO", "Cancelado"


ESTADOS_FINALES = {Estado.ENTREGADO, Estado.CON_NOVEDAD, Estado.CANCELADO}
ESTADOS_ENTREGADOS = {Estado.ENTREGADO, Estado.CON_NOVEDAD}
ESTADOS_ACTIVOS = {Estado.ASIGNADO, Estado.EN_TRANSITO}

# (estado origen, estado destino) -> roles que pueden ejecutar la transición.
TRANSICIONES = {
    (Estado.ASIGNADO, Estado.EN_TRANSITO): {Rol.CONDUCTOR},  # RF-20 salida
    (Estado.ASIGNADO, Estado.CANCELADO): {Rol.ADMINISTRADOR},  # RF-16
    (Estado.EN_TRANSITO, Estado.ENTREGADO): {Rol.INSTITUCION},  # RF-26
    (Estado.EN_TRANSITO, Estado.CON_NOVEDAD): {Rol.INSTITUCION, Rol.ADMINISTRADOR},  # RF-28
    # RF-28: hallazgo de la institución después de una recepción conforme.
    (Estado.ENTREGADO, Estado.CON_NOVEDAD): {Rol.INSTITUCION},
}


def puede_transicionar(origen, destino, rol):
    return rol in TRANSICIONES.get((origen, destino), set())


def destinos_posibles(origen, rol):
    return [d for (o, d), roles in TRANSICIONES.items() if o == origen and rol in roles]
