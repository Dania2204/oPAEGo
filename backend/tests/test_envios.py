"""RF-13 a RF-28: flujo completo de un envío a través de la API."""

import base64
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.envios.estados import Estado
from apps.envios.models import Envio, Novedad, Ubicacion

from .conftest import cliente_api, items_completos

pytestmark = pytest.mark.django_db

# PNG de 1×1 px para probar fotos en base64.
PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGA"
    "hKmMIQAAAABJRU5ErkJggg=="
)


def datos_envio(institucion, conductor, vehiculo=None):
    return {
        "institucion": institucion.pk,
        "conductor": conductor.pk,
        "vehiculo": vehiculo.pk if vehiculo else None,
        "programado_para": (timezone.now() + timedelta(hours=2)).isoformat(),
        "items": [
            {"producto": "Leche", "cantidad": "320", "unidad": "UNIDAD"},
            {"producto": "Fruta", "cantidad": "40.5", "unidad": "KG"},
        ],
    }


def test_flujo_completo(
    api_admin, api_conductor, api_institucion, institucion, conductor, vehiculo
):
    # RF-13 a RF-15: crear y asignar
    r = api_admin.post("/api/envios/", datos_envio(institucion, conductor, vehiculo), format="json")
    assert r.status_code == 201, r.data
    envio_id = r.data["id"]
    assert r.data["estado"] == Estado.ASIGNADO
    assert len(r.data["items"]) == 2
    codigo = r.data["codigo_verificacion"]

    # RF-19: el conductor ve su envío y el código para mostrarlo
    r = api_conductor.get("/api/envios/")
    assert [e["id"] for e in r.data["results"]] == [envio_id]
    assert r.data["results"][0]["codigo_verificacion"] == codigo

    # RF-24: la institución lo ve pero sin el código
    r = api_institucion.get(f"/api/envios/{envio_id}/")
    assert r.status_code == 200 and "codigo_verificacion" not in r.data

    # RF-20, RF-21, RF-22
    assert (
        api_conductor.post(
            f"/api/envios/{envio_id}/salida/",
            {"latitud": "1.21", "longitud": "-77.28"},
            format="json",
        ).data["estado"]
        == Estado.EN_TRANSITO
    )
    for k in range(3):
        r = api_conductor.post(
            f"/api/envios/{envio_id}/ubicaciones/",
            {"latitud": f"1.21{k}", "longitud": "-77.28", "velocidad_kmh": "30"},
            format="json",
        )
        assert r.status_code == 201
    r = api_conductor.post(
        f"/api/envios/{envio_id}/llegada/",
        {"latitud": "1.2168", "longitud": "-77.2883"},
        format="json",
    )
    assert r.data["llegada_en"] is not None

    # RF-25 a RF-27
    envio = Envio.objects.get(pk=envio_id)
    r = api_institucion.post(
        f"/api/envios/{envio_id}/confirmar/",
        {
            "items": items_completos(envio),
            "recibido_por_nombre": "María",
            "codigo_verificacion": codigo,
            "latitud": "1.2168",
            "longitud": "-77.2883",
            "foto": PNG,
        },
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["estado"] == Estado.ENTREGADO
    assert r.data["evidencia"]["es_integra"] is True
    envio.refresh_from_db()
    assert envio.tiene_registro_completo
    assert envio.evidencia.foto_sha256

    # RF-35: ruta recorrida y RF-34: historial
    assert len(api_admin.get(f"/api/envios/{envio_id}/ubicaciones/").data) == 5
    acciones = [h["accion"] for h in api_admin.get(f"/api/envios/{envio_id}/historial/").data]
    assert acciones == [
        Accion.ENVIO_CREADO,
        Accion.SALIDA,
        Accion.LLEGADA,
        Accion.RECEPCION_CONFIRMADA,
    ]


def test_crear_envio_valida_items(api_admin, institucion, conductor):
    datos = datos_envio(institucion, conductor)
    datos["items"] = []
    assert api_admin.post("/api/envios/", datos, format="json").status_code == 400


def test_vehiculo_de_otro_conductor_rechazado(api_admin, institucion, otro_conductor, vehiculo):
    r = api_admin.post(
        "/api/envios/", datos_envio(institucion, otro_conductor, vehiculo), format="json"
    )
    assert r.status_code == 400 and "vehiculo" in str(r.data)


def test_institucion_desactivada_rechazada(api_admin, institucion, conductor):
    institucion.activo = False
    institucion.save()
    assert (
        api_admin.post(
            "/api/envios/", datos_envio(institucion, conductor), format="json"
        ).status_code
        == 400
    )


def test_conductor_ajeno_no_ve_ni_opera_el_envio(envio, otro_conductor):
    cliente = cliente_api(otro_conductor.usuario)
    assert cliente.get(f"/api/envios/{envio.pk}/").status_code == 404
    r = cliente.post(
        f"/api/envios/{envio.pk}/salida/", {"latitud": "1", "longitud": "-77"}, format="json"
    )
    assert r.status_code == 404


def test_institucion_ajena_no_confirma(envio_en_transito, responsable_otra):
    cliente = cliente_api(responsable_otra.usuario)
    r = cliente.post(f"/api/envios/{envio_en_transito.pk}/confirmar/", {}, format="json")
    assert r.status_code == 404


def test_codigo_de_verificacion_incorrecto(envio_en_transito, api_institucion):
    r = api_institucion.post(
        f"/api/envios/{envio_en_transito.pk}/confirmar/",
        {
            "items": items_completos(envio_en_transito),
            "recibido_por_nombre": "María",
            "codigo_verificacion": "000000"
            if envio_en_transito.codigo_verificacion != "000000"
            else "111111",
        },
        format="json",
    )
    assert r.status_code == 400 and "codigo_verificacion" in r.data


def test_recepcion_con_faltantes_queda_con_novedad(envio_en_transito, api_institucion):
    items = items_completos(envio_en_transito)
    items[0]["cantidad_recibida"] = "90"
    r = api_institucion.post(
        f"/api/envios/{envio_en_transito.pk}/confirmar/",
        {
            "items": items,
            "recibido_por_nombre": "María",
            "codigo_verificacion": envio_en_transito.codigo_verificacion,
        },
        format="json",
    )
    assert r.status_code == 200
    assert r.data["estado"] == Estado.CON_NOVEDAD
    novedad = Novedad.objects.get(envio=envio_en_transito)
    assert novedad.tipo == Novedad.Tipo.FALTANTE and "programado 100" in novedad.descripcion


def test_no_se_confirma_un_envio_sin_salida(envio, api_institucion):
    r = api_institucion.post(
        f"/api/envios/{envio.pk}/confirmar/",
        {
            "items": items_completos(envio),
            "recibido_por_nombre": "M",
            "codigo_verificacion": envio.codigo_verificacion,
        },
        format="json",
    )
    assert r.status_code == 400


def test_novedad_del_conductor_con_foto_multipart(envio_en_transito, api_conductor):
    from django.core.files.uploadedfile import SimpleUploadedFile

    foto = SimpleUploadedFile("f.png", base64.b64decode(PNG), content_type="image/png")
    r = api_conductor.post(
        f"/api/envios/{envio_en_transito.pk}/novedades/",
        {"tipo": "DANO", "descripcion": "Se rompió una caja", "foto": foto},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    assert r.data["origen"] == Novedad.Origen.TRAYECTO and r.data["foto"]
    # La novedad del trayecto no cambia el estado.
    envio_en_transito.refresh_from_db()
    assert envio_en_transito.estado == Estado.EN_TRANSITO


def test_hallazgo_posterior_pasa_entregado_a_con_novedad(envio_en_transito, api_institucion):
    api_institucion.post(
        f"/api/envios/{envio_en_transito.pk}/confirmar/",
        {
            "items": items_completos(envio_en_transito),
            "recibido_por_nombre": "M",
            "codigo_verificacion": envio_en_transito.codigo_verificacion,
        },
        format="json",
    )
    r = api_institucion.post(
        f"/api/envios/{envio_en_transito.pk}/novedades/",
        {"tipo": "DANO", "descripcion": "Leche vencida"},
        format="json",
    )
    assert r.status_code == 201
    envio_en_transito.refresh_from_db()
    assert envio_en_transito.estado == Estado.CON_NOVEDAD


def test_modificar_exige_motivo_y_solo_antes_de_salida(envio, api_admin, institucion):
    datos = {
        "institucion": institucion.pk,
        "programado_para": timezone.now().isoformat(),
        "items": [{"producto": "Arroz", "cantidad": "10", "unidad": "KG"}],
    }
    assert api_admin.put(f"/api/envios/{envio.pk}/", datos, format="json").status_code == 400
    datos["motivo"] = "Cambio de menú"
    r = api_admin.put(f"/api/envios/{envio.pk}/", datos, format="json")
    assert r.status_code == 200 and r.data["items"][0]["producto"] == "Arroz"
    registro = RegistroAuditoria.objects.get(accion=Accion.ENVIO_EDITADO)
    assert registro.datos["motivo"] == "Cambio de menú"
    assert registro.datos["antes"]["items"][0]["producto"] == "Leche"


def test_reasignar_y_cancelar(envio, api_admin, otro_conductor):
    r = api_admin.post(
        f"/api/envios/{envio.pk}/reasignar/",
        {"conductor": otro_conductor.pk, "motivo": "Incapacidad"},
        format="json",
    )
    assert r.status_code == 200 and r.data["conductor_id"] == otro_conductor.pk
    r = api_admin.post(f"/api/envios/{envio.pk}/cancelar/", {"motivo": "Paro"}, format="json")
    assert r.data["estado"] == Estado.CANCELADO and r.data["motivo_cancelacion"] == "Paro"


def test_no_se_cancela_despues_de_la_salida(envio_en_transito, api_admin):
    r = api_admin.post(
        f"/api/envios/{envio_en_transito.pk}/cancelar/", {"motivo": "x"}, format="json"
    )
    assert r.status_code == 400


def test_cerrar_con_novedad(envio_en_transito, api_admin):
    r = api_admin.post(
        f"/api/envios/{envio_en_transito.pk}/cerrar-con-novedad/",
        {"motivo": "Accidente"},
        format="json",
    )
    assert r.data["estado"] == Estado.CON_NOVEDAD


def test_filtros_rf17(api_admin, envio, envio_en_transito):
    r = api_admin.get("/api/envios/", {"estado": Estado.EN_TRANSITO})
    assert [e["id"] for e in r.data["results"]] == [envio_en_transito.pk]
    hoy = timezone.localdate().isoformat()
    r = api_admin.get("/api/envios/", {"fecha_desde": hoy, "conductor": envio.conductor_id})
    assert r.data["count"] == 1


def test_ubicacion_anterior_a_la_salida_rechazada(envio_en_transito, api_conductor):
    antes = (envio_en_transito.salida_en - timedelta(hours=1)).isoformat()
    r = api_conductor.post(
        f"/api/envios/{envio_en_transito.pk}/ubicaciones/",
        {"latitud": "1", "longitud": "-77", "ocurrido_en": antes},
        format="json",
    )
    assert r.status_code == 400
    assert Ubicacion.objects.filter(envio=envio_en_transito).count() == 1


def test_fecha_futura_rechazada(envio, api_conductor):
    futuro = (timezone.now() + timedelta(hours=2)).isoformat()
    r = api_conductor.post(
        f"/api/envios/{envio.pk}/salida/",
        {"latitud": "1", "longitud": "-77", "ocurrido_en": futuro},
        format="json",
    )
    assert r.status_code == 400


def test_encabezado_idempotente_api_directa(envio_en_transito, api_conductor):
    url = f"/api/envios/{envio_en_transito.pk}/ubicaciones/"
    cabecera = {"HTTP_X_OPERACION_ID": "6f1c1b4e-7a0e-4b8f-9b11-2d0f3f7b9a01"}
    for _ in range(3):
        api_conductor.post(url, {"latitud": "1.3", "longitud": "-77.3"}, format="json", **cabecera)
    assert Ubicacion.objects.filter(envio=envio_en_transito).count() == 2  # salida + 1
