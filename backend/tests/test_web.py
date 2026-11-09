"""Panel web del administrador: formularios que usan las mismas reglas de la API."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalogo.models import Institucion
from apps.envios import servicios
from apps.envios.estados import Estado
from apps.envios.models import Envio, Novedad

pytestmark = pytest.mark.django_db


PAGINAS = [
    "/panel/",
    "/indicadores/",
    "/indicadores/?desde=2026-01-01&hasta=2026-12-31",
    "/novedades/",
    "/novedades/?estado=todas",
    "/envios/",
    "/envios/?vista=hoy",
    "/envios/?vista=en_ruta&estado=EN_TRANSITO",
    "/envios/nuevo/",
    "/envios/programar/",
    "/instituciones/",
    "/instituciones/nuevo/",
    "/conductores/",
    "/conductores/nuevo/",
    "/vehiculos/",
    "/vehiculos/nuevo/",
    "/responsables/",
    "/responsables/nuevo/",
    "/usuarios/",
    "/usuarios/nuevo/",
    "/auditoria/",
    "/reportes/",
    "/reportes/?desde=2026-01-01",
]


@pytest.mark.parametrize("url", PAGINAS)
def test_paginas_del_panel(web_admin, envio, url):
    assert web_admin.get(url).status_code == 200


def test_detalle_de_envio(web_admin, envio_en_transito):
    r = web_admin.get(f"/envios/{envio_en_transito.pk}/")
    assert r.status_code == 200
    assert envio_en_transito.codigo in r.content.decode()


def test_crear_envio_desde_la_web(web_admin, institucion, conductor, vehiculo):
    datos = {
        "uuid_cliente": str(uuid.uuid4()),
        "institucion": institucion.pk,
        "programado_para": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        "conductor": conductor.pk,
        "vehiculo": vehiculo.pk,
        "observaciones": "",
        "item_producto": ["Leche", "Pan"],
        "item_cantidad": ["10", "20"],
        "item_unidad": ["UNIDAD", "UNIDAD"],
    }
    r = web_admin.post("/envios/nuevo/", datos)
    assert r.status_code == 302, r.content.decode()[:2000]
    envio = Envio.objects.get()
    assert envio.estado == Estado.ASIGNADO and envio.items.count() == 2
    # Doble envío del mismo formulario (doble clic o reintento): no duplica.
    web_admin.post("/envios/nuevo/", datos)
    assert Envio.objects.count() == 1


def test_errores_de_la_api_se_muestran_en_el_formulario(web_admin, institucion, conductor):
    r = web_admin.post(
        "/envios/nuevo/",
        {
            "uuid_cliente": str(uuid.uuid4()),
            "institucion": institucion.pk,
            "programado_para": "2026-10-10T08:00",
            "conductor": conductor.pk,
        },
    )
    assert r.status_code == 200
    assert "al menos un alimento" in r.content.decode()


def test_registrar_y_desactivar_institucion(web_admin):
    r = web_admin.post(
        "/instituciones/nuevo/",
        {
            "uuid_cliente": str(uuid.uuid4()),
            "nombre": "IEM Prueba",
            "sede": "Principal",
            "direccion": "Calle 1",
            "latitud": "1.2",
            "longitud": "-77.2",
        },
    )
    assert r.status_code == 302
    institucion = Institucion.objects.get(nombre="IEM Prueba")
    web_admin.post(f"/instituciones/{institucion.pk}/estado/")
    institucion.refresh_from_db()
    assert not institucion.activo


def test_cancelar_desde_detalle(web_admin, envio):
    r = web_admin.post(
        f"/envios/{envio.pk}/cancelar/", {"uuid_cliente": str(uuid.uuid4()), "motivo": "Paro"}
    )
    assert r.status_code == 302
    envio.refresh_from_db()
    assert envio.estado == Estado.CANCELADO


def test_pwa_disponible(client):
    assert client.get("/sw.js")["Content-Type"] == "application/javascript"
    assert client.get("/manifest.webmanifest").status_code == 200


# ----------------------------------------------------------------- rediseño
HX = {"HTTP_HX_REQUEST": "true"}


def hx(destino):
    return {**HX, "HTTP_HX_TARGET": destino}


def test_mapa_antiguo_redirige_a_hoy(web_admin):
    r = web_admin.get("/monitoreo/")
    assert r.status_code == 302 and r["Location"] == "/panel/"


def test_detalle_en_panel_lateral_devuelve_solo_el_fragmento(web_admin, envio):
    r = web_admin.get(f"/envios/{envio.pk}/", **hx("panel-contenido"))
    html = r.content.decode()
    assert r.status_code == 200
    assert envio.codigo in html and "<html" not in html
    assert "panel-cabeza" in html
    assert "HX-Target" in r["Vary"]


def test_hoy_parcial_para_refresco_periodico(web_admin, envio_en_transito):
    r = web_admin.get("/panel/", **hx("estado-hoy"))
    html = r.content.decode()
    assert "<html" not in html and "datos-hoy" in html
    assert envio_en_transito.codigo in html


def test_hoy_muestra_lo_que_requiere_atencion(web_admin, envio, conductor):
    envio.programado_para = timezone.now() - timedelta(hours=3)
    envio.save()
    r = web_admin.get("/panel/")
    html = r.content.decode()
    assert "Requiere atención" in html and "Retrasado" in html


def test_filtros_de_envios_devuelven_solo_resultados(web_admin, envio, envio_en_transito):
    r = web_admin.get("/envios/?vista=en_ruta", **hx("resultados"))
    html = r.content.decode()
    assert "<html" not in html and 'id="vista-actual"' in html


def test_crear_envio_desde_el_panel(web_admin, institucion, conductor):
    r = web_admin.post(
        "/envios/nuevo/",
        {
            "uuid_cliente": str(uuid.uuid4()),
            "institucion": institucion.pk,
            "programado_para": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "conductor": conductor.pk,
            "item_producto": ["Arroz"],
            "item_cantidad": ["5"],
            "item_unidad": ["KG"],
        },
        **hx("panel-contenido"),
    )
    envio = Envio.objects.get()
    assert r.status_code == 200
    assert r["HX-Push-Url"] == f"/envios/{envio.pk}/"
    assert "envios-actualizados" in r["HX-Trigger"]
    assert envio.codigo in r.content.decode()


def test_reasignar_desde_el_panel(web_admin, envio, otro_conductor):
    r = web_admin.post(
        f"/envios/{envio.pk}/reasignar/",
        {"uuid_cliente": str(uuid.uuid4()), "conductor": otro_conductor.pk, "motivo": "Turno"},
        **hx("panel-contenido"),
    )
    envio.refresh_from_db()
    assert envio.conductor == otro_conductor
    assert "reasignado" in r.content.decode()


def test_duplicar_envio_precarga_el_formulario(web_admin, envio):
    r = web_admin.get(f"/envios/nuevo/?duplicar={envio.pk}", **hx("panel-contenido"))
    html = r.content.decode()
    assert f"Duplicar {envio.codigo}" in html
    assert 'value="Leche"' in html


def test_programar_envios_en_lote(web_admin, admin, institucion, otra_institucion, conductor):
    lote = str(uuid.uuid4())
    manana = (timezone.localdate() + timedelta(days=1)).isoformat()
    datos = {
        "uuid_lote": lote,
        "fecha": manana,
        "hora": "07:30",
        "instituciones": [institucion.pk, otra_institucion.pk],
        f"conductor_{institucion.pk}": conductor.pk,
        f"conductor_{otra_institucion.pk}": conductor.pk,
        "item_producto": ["Leche", "Pan"],
        "item_cantidad": ["300", "300"],
        "item_unidad": ["UNIDAD", "UNIDAD"],
    }
    r = web_admin.post("/envios/programar/", datos)
    assert r.status_code == 302
    assert Envio.objects.count() == 2
    assert all(e.items.count() == 2 for e in Envio.objects.all())
    assert {
        timezone.localtime(e.programado_para).strftime("%H:%M") for e in Envio.objects.all()
    } == {"07:30"}
    # Reenviar el mismo formulario no duplica.
    web_admin.post("/envios/programar/", datos)
    assert Envio.objects.count() == 2


def test_programar_reporta_errores_por_institucion(web_admin, institucion, conductor):
    r = web_admin.post(
        "/envios/programar/",
        {
            "uuid_lote": str(uuid.uuid4()),
            "fecha": timezone.localdate().isoformat(),
            "hora": "08:00",
            "instituciones": [institucion.pk],
            "item_producto": ["Leche"],
            "item_cantidad": ["10"],
            "item_unidad": ["UNIDAD"],
        },
    )
    assert r.status_code == 200
    assert Envio.objects.count() == 0
    assert "conductor" in r.content.decode().lower()


def test_programar_prellena_ultimo_conductor(web_admin, envio):
    html = web_admin.get("/envios/programar/").content.decode()
    assert f'value="{envio.conductor_id}" selected' in html


def test_bandeja_de_novedades_y_atender(web_admin, envio_en_transito, conductor):
    novedad = servicios.reportar_novedad(
        conductor.usuario, envio_en_transito, tipo="RETRASO", descripcion="Trancón en la vía"
    )
    r = web_admin.get(f"/novedades/{novedad.pk}/", **hx("novedad-detalle"))
    assert "Trancón en la vía" in r.content.decode()
    r = web_admin.post(f"/novedades/{novedad.pk}/", **hx("novedad-detalle"))
    assert "novedades-actualizadas" in r["HX-Trigger"]
    assert Novedad.objects.get(pk=novedad.pk).leida_en is not None


def test_catalogo_guardado_desde_el_panel_cierra_y_refresca(web_admin):
    r = web_admin.post(
        "/instituciones/nuevo/",
        {
            "uuid_cliente": str(uuid.uuid4()),
            "nombre": "IEM Panel",
            "sede": "Principal",
            "direccion": "Calle 2",
            "latitud": "1.21",
            "longitud": "-77.28",
        },
        **hx("panel-contenido"),
    )
    assert "cerrar-panel" in r["HX-Trigger"] and "catalogo-actualizado" in r["HX-Trigger"]
    assert Institucion.objects.filter(nombre="IEM Panel").exists()


def test_indicadores_parcial(web_admin, envio):
    r = web_admin.get("/indicadores/?desde=2026-01-01", **hx("resultado-indicadores"))
    html = r.content.decode()
    assert "<html" not in html and "serie-indicadores" in html


def test_cabecera_govco_y_entidad(web_admin):
    html = web_admin.get("/panel/").content.decode()
    assert "GOV.CO" in html and "Alcaldía de Pasto" in html and "Work+Sans" in html
