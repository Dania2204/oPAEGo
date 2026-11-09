"""RF-18: transiciones de estado permitidas por rol."""

import pytest

from apps.cuentas.models import Rol
from apps.envios.estados import Estado, destinos_posibles, puede_transicionar


@pytest.mark.parametrize(
    ("origen", "destino", "rol", "esperado"),
    [
        (Estado.ASIGNADO, Estado.EN_TRANSITO, Rol.CONDUCTOR, True),
        (Estado.ASIGNADO, Estado.EN_TRANSITO, Rol.ADMINISTRADOR, False),
        (Estado.ASIGNADO, Estado.CANCELADO, Rol.ADMINISTRADOR, True),
        (Estado.ASIGNADO, Estado.CANCELADO, Rol.CONDUCTOR, False),
        (Estado.EN_TRANSITO, Estado.ENTREGADO, Rol.INSTITUCION, True),
        (Estado.EN_TRANSITO, Estado.ENTREGADO, Rol.CONDUCTOR, False),
        (Estado.EN_TRANSITO, Estado.CON_NOVEDAD, Rol.INSTITUCION, True),
        (Estado.EN_TRANSITO, Estado.CON_NOVEDAD, Rol.ADMINISTRADOR, True),
        (Estado.EN_TRANSITO, Estado.CANCELADO, Rol.ADMINISTRADOR, False),
        (Estado.ENTREGADO, Estado.CON_NOVEDAD, Rol.INSTITUCION, True),
        (Estado.ENTREGADO, Estado.EN_TRANSITO, Rol.CONDUCTOR, False),
        (Estado.CANCELADO, Estado.ASIGNADO, Rol.ADMINISTRADOR, False),
    ],
)
def test_transiciones(origen, destino, rol, esperado):
    assert puede_transicionar(origen, destino, rol) is esperado


def test_estados_son_los_del_documento():
    assert {e.value for e in Estado} == {
        "ASIGNADO",
        "EN_TRANSITO",
        "ENTREGADO",
        "CON_NOVEDAD",
        "CANCELADO",
    }


def test_estados_finales_sin_salida_para_conductor():
    for estado in (Estado.ENTREGADO, Estado.CON_NOVEDAD, Estado.CANCELADO):
        assert destinos_posibles(estado, Rol.CONDUCTOR) == []
