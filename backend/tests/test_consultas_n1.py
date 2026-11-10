"""Sin consultas N+1: el número de consultas SQL de los listados no crece con
la cantidad de envíos o de conductores (los endpoints que la app y el mapa
consultan cada pocos segundos)."""

from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.models import Conductor, Vehiculo
from apps.cuentas.models import Rol
from apps.envios import servicios
from apps.monitoreo import en_vivo

from .conftest import ITEMS, cliente_api, crear_usuario


def _consultas(cliente, url):
    with CaptureQueriesContext(connection) as ctx:
        respuesta = cliente.get(url)
    assert respuesta.status_code == 200
    return len(ctx.captured_queries), respuesta.json()


def _crear_envios(admin, institucion, conductor, vehiculo, n, en_transito=False):
    for _ in range(n):
        envio = servicios.crear_envio(
            admin,
            institucion=institucion,
            conductor=conductor,
            vehiculo=vehiculo,
            programado_para=timezone.now() + timedelta(hours=1),
            items=ITEMS,
        )
        if en_transito:
            servicios.registrar_salida(
                conductor.usuario, envio, latitud=Decimal("1.21"), longitud=Decimal("-77.28")
            )


def _crece_igual(medir, agregar):
    """Mide, agrega datos y vuelve a medir: las consultas deben ser las mismas."""
    antes, datos_antes = medir()
    agregar()
    despues, datos_despues = medir()
    assert datos_despues != datos_antes  # sí aparecieron más registros
    assert despues == antes, f"{antes} consultas con pocos datos, {despues} con más"


def test_listado_de_envios_admin(admin, institucion, conductor, vehiculo):
    cliente = cliente_api(admin)
    url = reverse("api:envio-list")
    _crear_envios(admin, institucion, conductor, vehiculo, 1)
    _crece_igual(
        lambda: _consultas(cliente, url),
        lambda: _crear_envios(admin, institucion, conductor, vehiculo, 5),
    )


def test_listado_de_envios_conductor(admin, institucion, conductor, vehiculo):
    cliente = cliente_api(conductor.usuario)
    url = reverse("api:envio-list")
    _crear_envios(admin, institucion, conductor, vehiculo, 1)
    _crece_igual(
        lambda: _consultas(cliente, url),
        lambda: _crear_envios(admin, institucion, conductor, vehiculo, 5, en_transito=True),
    )


def test_envios_en_transito_del_mapa(admin, institucion, conductor, vehiculo):
    cliente = cliente_api(admin)
    url = reverse("api:monitoreo_en_transito")
    _crear_envios(admin, institucion, conductor, vehiculo, 1, en_transito=True)
    _crece_igual(
        lambda: _consultas(cliente, url),
        lambda: _crear_envios(admin, institucion, conductor, vehiculo, 4, en_transito=True),
    )


def test_conductores_en_vivo(admin, conductor, vehiculo):
    cliente = cliente_api(admin)
    url = reverse("api:monitoreo_conductores_en_vivo")
    en_vivo.actualizar_posicion(
        conductor.usuario, latitud=Decimal("1.21"), longitud=Decimal("-77.28")
    )

    def conectar_mas():
        for i in range(4):
            u = crear_usuario(f"vivo{i}@test.co", Rol.CONDUCTOR)
            c = Conductor.objects.create(usuario=u, numero_documento=f"20{i}", telefono="3")
            Vehiculo.objects.create(
                placa=f"XYZ{i}00", tipo="Furgón", capacidad_kg=Decimal("500"), conductor=c
            )
            en_vivo.actualizar_posicion(u, latitud=Decimal("1.2"), longitud=Decimal("-77.2"))

    _crece_igual(lambda: _consultas(cliente, url), conectar_mas)


def test_ruta_del_mapa_ultimos_puntos_en_orden(
    api_admin, envio_en_transito, conductor, monkeypatch
):
    from apps.envios.models import Envio
    from apps.monitoreo import consultas

    ahora = timezone.now()
    Envio.objects.filter(pk=envio_en_transito.pk).update(salida_en=ahora - timedelta(hours=1))
    envio_en_transito.refresh_from_db()
    # Llegan desordenados (sincronización sin conexión).
    for minutos, lat in [(10, "1.30"), (40, "1.10"), (20, "1.25"), (30, "1.20")]:
        servicios.registrar_ubicacion(
            conductor.usuario,
            envio_en_transito,
            latitud=lat,
            longitud="-77.28",
            ocurrido_en=ahora - timedelta(minutes=minutos),
        )
    monkeypatch.setattr(consultas, "PUNTOS_RUTA_MAPA", 3)

    datos = api_admin.get(reverse("api:monitoreo_en_transito")).json()
    # Los 3 más recientes, del más viejo al más nuevo; el último es el punto
    # de la salida (1.21), registrado después de los demás.
    assert [lat for lat, _ in datos[0]["ruta"]] == [1.25, 1.3, 1.21]
    assert datos[0]["posicion"] == [1.21, -77.28]
