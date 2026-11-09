"""RF-38 / RNF-21: operaciones capturadas sin conexión y sincronizadas después."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.envios.estados import Estado
from apps.envios.models import Envio, Ubicacion
from apps.monitoreo import kpis
from apps.sincronizacion.models import OperacionCliente

from .conftest import items_completos

pytestmark = pytest.mark.django_db
URL = "/api/sincronizacion/lote/"


def op(tipo, datos, hace_min, uid=None):
    return {
        "uuid_cliente": str(uid or uuid.uuid4()),
        "tipo": tipo,
        "ocurrido_en": (timezone.now() - timedelta(minutes=hace_min)).isoformat(),
        "datos": datos,
    }


def test_lote_del_conductor_en_orden_cronologico(envio, api_conductor):
    # Llegan desordenadas: el servidor las aplica por ocurrido_en.
    operaciones = [
        op("envio.llegada", {"envio": envio.pk, "latitud": "1.2168", "longitud": "-77.2883"}, 10),
        op("envio.ubicacion", {"envio": envio.pk, "latitud": "1.215", "longitud": "-77.285"}, 30),
        op("envio.salida", {"envio": envio.pk, "latitud": "1.21", "longitud": "-77.28"}, 45),
    ]
    r = api_conductor.post(URL, {"operaciones": operaciones}, format="json")
    assert r.status_code == 200
    assert [x["resultado"] for x in r.data["resultados"]] == ["ok", "ok", "ok"]
    envio.refresh_from_db()
    assert envio.estado == Estado.EN_TRANSITO
    # Se conserva la hora real del evento, no la de sincronización.
    assert timezone.now() - envio.salida_en > timedelta(minutes=44)
    salida = RegistroAuditoria.objects.get(accion=Accion.SALIDA)
    assert salida.diferido is True


def test_reenviar_el_lote_no_duplica(envio_en_transito, api_conductor):
    lote = {
        "operaciones": [
            op(
                "envio.ubicacion",
                {"envio": envio_en_transito.pk, "latitud": "1.3", "longitud": "-77.3"},
                0,
            )
            for _ in range(3)
        ]
    }
    primera = api_conductor.post(URL, lote, format="json").data["resultados"]
    segunda = api_conductor.post(URL, lote, format="json").data["resultados"]
    assert [x["resultado"] for x in primera] == ["ok"] * 3
    assert [x["resultado"] for x in segunda] == ["duplicado"] * 3
    assert Ubicacion.objects.filter(envio=envio_en_transito).count() == 4  # salida + 3


def test_operacion_invalida_se_rechaza_y_se_audita(envio, api_admin, api_conductor):
    # Mientras el conductor estaba sin conexión, el administrador canceló el envío.
    api_admin.post(f"/api/envios/{envio.pk}/cancelar/", {"motivo": "Paro"}, format="json")
    uid = uuid.uuid4()
    r = api_conductor.post(
        URL,
        {
            "operaciones": [
                op(
                    "envio.salida",
                    {"envio": envio.pk, "latitud": "1.2", "longitud": "-77.2"},
                    20,
                    uid,
                )
            ]
        },
        format="json",
    )
    resultado = r.data["resultados"][0]
    assert resultado["resultado"] == "rechazado"
    assert "estado" in str(resultado["respuesta"])
    assert OperacionCliente.objects.get(uuid_cliente=uid).resultado == "rechazado"
    assert RegistroAuditoria.objects.filter(
        accion=Accion.SINCRONIZACION_RECHAZADA, envio=envio
    ).exists()
    # Reintentar devuelve el mismo rechazo sin volver a procesar.
    r = api_conductor.post(
        URL,
        {
            "operaciones": [
                op(
                    "envio.salida",
                    {"envio": envio.pk, "latitud": "1.2", "longitud": "-77.2"},
                    20,
                    uid,
                )
            ]
        },
        format="json",
    )
    assert r.data["resultados"][0]["resultado"] == "duplicado"


def test_uuid_de_otro_usuario_no_se_reutiliza(envio_en_transito, api_conductor, api_admin):
    uid = uuid.uuid4()
    api_conductor.post(
        URL,
        {
            "operaciones": [
                op(
                    "envio.ubicacion",
                    {"envio": envio_en_transito.pk, "latitud": "1", "longitud": "-77"},
                    1,
                    uid,
                )
            ]
        },
        format="json",
    )
    r = api_admin.post(
        URL,
        {
            "operaciones": [
                op("envio.cancelar", {"envio": envio_en_transito.pk, "motivo": "x"}, 1, uid)
            ]
        },
        format="json",
    )
    assert r.data["resultados"][0]["resultado"] == "rechazado"


def test_entrega_sincronizada_tarde_cuenta_a_tiempo(envio_en_transito, api_institucion):
    """La entrega ocurrió a tiempo aunque se sincronizó horas después."""
    envio_en_transito.programado_para = timezone.now() - timedelta(hours=3)
    envio_en_transito.save()
    r = api_institucion.post(
        URL,
        {
            "operaciones": [
                op(
                    "envio.confirmar",
                    {
                        "envio": envio_en_transito.pk,
                        "items": items_completos(envio_en_transito),
                        "recibido_por_nombre": "María",
                        "codigo_verificacion": envio_en_transito.codigo_verificacion,
                    },
                    200,
                )
            ]
        },
        format="json",
    )
    assert r.data["resultados"][0]["resultado"] == "ok", r.data
    envio_en_transito.refresh_from_db()
    assert envio_en_transito.entregado_a_tiempo is True
    assert kpis.calcular().entregas_a_tiempo == 1


def test_admin_crea_institucion_y_envio_sin_conexion_con_referencia(api_admin, conductor):
    uid_institucion = str(uuid.uuid4())
    r = api_admin.post(
        URL,
        {
            "operaciones": [
                op(
                    "envio.crear",
                    {
                        "institucion": uid_institucion,
                        "conductor": conductor.pk,
                        "programado_para": timezone.now().isoformat(),
                        "items": [{"producto": "Arroz", "cantidad": "5", "unidad": "KG"}],
                    },
                    5,
                ),
                op(
                    "institucion.crear",
                    {
                        "nombre": "IEM Nueva",
                        "sede": "Principal",
                        "direccion": "Cra 1",
                        "latitud": "1.2",
                        "longitud": "-77.2",
                    },
                    10,
                    uid_institucion,
                ),
            ]
        },
        format="json",
    )
    resultados = {x["tipo"]: x for x in r.data["resultados"]}
    assert resultados["institucion.crear"]["resultado"] == "ok"
    assert resultados["envio.crear"]["resultado"] == "ok", resultados
    envio = Envio.objects.get(pk=resultados["envio.crear"]["respuesta"]["id"])
    assert envio.institucion.nombre == "IEM Nueva"


def test_operacion_desconocida(api_admin):
    r = api_admin.post(URL, {"operaciones": [op("envio.borrar", {}, 1)]}, format="json")
    assert r.status_code == 400


def test_configuracion_para_clientes(api_conductor):
    r = api_conductor.get("/api/sincronizacion/configuracion/")
    assert r.status_code == 200 and "envio.ubicacion" in r.data["operaciones"]
