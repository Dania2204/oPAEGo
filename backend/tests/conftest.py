from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalogo.models import Conductor, Institucion, ResponsableRecepcion, Vehiculo
from apps.cuentas.models import Rol, Usuario
from apps.cuentas.tokens import emitir_tokens
from apps.envios import servicios

CLAVE = "Clave-Segura-2026"


@pytest.fixture(autouse=True)
def _contadores_limpios():
    """Los límites de intentos (apps/cuentas/limite.py) no pasan de una prueba a otra."""
    cache.clear()
    yield
    cache.clear()


def crear_usuario(email, rol, **extra):
    return Usuario.objects.create_user(
        email=email,
        password=CLAVE,
        rol=rol,
        first_name=extra.pop("nombre", "Nombre"),
        last_name="Apellido",
        **extra,
    )


@pytest.fixture
def admin(db):
    return crear_usuario("admin@test.co", Rol.ADMINISTRADOR, nombre="Admin")


@pytest.fixture
def institucion(db):
    return Institucion.objects.create(
        nombre="Escuela Normal Superior",
        sede="Principal",
        direccion="Calle 18",
        latitud=Decimal("1.216800"),
        longitud=Decimal("-77.288300"),
    )


@pytest.fixture
def otra_institucion(db):
    return Institucion.objects.create(
        nombre="Otra IEM",
        sede="Principal",
        direccion="Barrio X",
        latitud=Decimal("1.200000"),
        longitud=Decimal("-77.260000"),
    )


@pytest.fixture
def conductor(db):
    u = crear_usuario("conductor@test.co", Rol.CONDUCTOR, nombre="Carlos")
    return Conductor.objects.create(usuario=u, numero_documento="1001", telefono="300")


@pytest.fixture
def otro_conductor(db):
    u = crear_usuario("conductor2@test.co", Rol.CONDUCTOR, nombre="Luisa")
    return Conductor.objects.create(usuario=u, numero_documento="1002", telefono="301")


@pytest.fixture
def vehiculo(conductor):
    return Vehiculo.objects.create(
        placa="ABC123", tipo="Furgón", capacidad_kg=Decimal("1000"), conductor=conductor
    )


@pytest.fixture
def responsable(institucion):
    u = crear_usuario("recibe@test.co", Rol.INSTITUCION, nombre="María")
    return ResponsableRecepcion.objects.create(usuario=u, institucion=institucion, cargo="Almacén")


@pytest.fixture
def responsable_otra(otra_institucion):
    u = crear_usuario("recibe2@test.co", Rol.INSTITUCION, nombre="Pedro")
    return ResponsableRecepcion.objects.create(
        usuario=u, institucion=otra_institucion, cargo="Rector"
    )


ITEMS = [
    {"producto": "Leche", "cantidad": Decimal("100"), "unidad": "UNIDAD"},
    {"producto": "Pan", "cantidad": Decimal("100"), "unidad": "UNIDAD"},
]


@pytest.fixture
def envio(admin, institucion, conductor, vehiculo):
    return servicios.crear_envio(
        admin,
        institucion=institucion,
        conductor=conductor,
        vehiculo=vehiculo,
        programado_para=timezone.now() + timedelta(hours=1),
        items=ITEMS,
    )


@pytest.fixture
def envio_en_transito(envio, conductor):
    servicios.registrar_salida(
        conductor.usuario, envio, latitud=Decimal("1.21"), longitud=Decimal("-77.28")
    )
    envio.refresh_from_db()
    return envio


def cliente_api(usuario):
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION="Bearer " + emitir_tokens(usuario)["access"])
    return cliente


@pytest.fixture
def api_admin(admin):
    return cliente_api(admin)


@pytest.fixture
def api_conductor(conductor):
    return cliente_api(conductor.usuario)


@pytest.fixture
def api_institucion(responsable):
    return cliente_api(responsable.usuario)


@pytest.fixture
def web_admin(client, admin):
    from apps.cuentas.tokens import poner_cookies

    class _R(dict):
        def set_cookie(self, clave, valor, **kwargs):
            self[clave] = valor

    cookies = _R()
    poner_cookies(cookies, emitir_tokens(admin))
    for clave, valor in cookies.items():
        client.cookies[clave] = valor
    return client


def items_completos(envio):
    return [{"item": i.pk, "cantidad_recibida": str(i.cantidad)} for i in envio.items.all()]
