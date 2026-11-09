"""Mapa en vivo de los conductores (modo de prueba)."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.cuentas.tokens import emitir_tokens
from apps.monitoreo.models import PosicionEnVivo

from .conftest import CLAVE

URL_POSICION = "/api/monitoreo/mi-posicion/"
URL_EN_VIVO = "/api/monitoreo/conductores-en-vivo/"


def test_conductor_publica_y_admin_lo_ve(api_conductor, api_admin, conductor, vehiculo):
    datos = {"latitud": "1.214000", "longitud": "-77.280000", "rumbo": 90, "velocidad_kmh": "32.5"}
    assert api_conductor.post(URL_POSICION, datos, format="json").status_code == 204
    datos["latitud"] = "1.214500"
    assert api_conductor.post(URL_POSICION, datos, format="json").status_code == 204
    assert PosicionEnVivo.objects.count() == 1  # una fila por conductor (upsert)

    r = api_admin.get(URL_EN_VIVO)
    assert r.status_code == 200
    [c] = r.json()
    assert c["id"] == conductor.pk
    assert c["posicion"] == [1.2145, -77.28]
    assert c["rumbo"] == 90 and c["placa"] == "ABC123"


def test_solo_el_conductor_publica_y_solo_el_admin_consulta(
    api_admin, api_institucion, api_conductor
):
    datos = {"latitud": "1.2", "longitud": "-77.2"}
    assert api_admin.post(URL_POSICION, datos, format="json").status_code == 403
    assert api_institucion.post(URL_POSICION, datos, format="json").status_code == 403
    assert api_conductor.get(URL_EN_VIVO).status_code == 403
    assert api_institucion.get(URL_EN_VIVO).status_code == 403


def test_coordenadas_invalidas(api_conductor):
    r = api_conductor.post(URL_POSICION, {"latitud": "95", "longitud": "-77.2"}, format="json")
    assert r.status_code == 400 and "latitud" in r.json()


def test_posicion_vieja_no_se_muestra(api_conductor, api_admin):
    api_conductor.post(URL_POSICION, {"latitud": "1.2", "longitud": "-77.2"}, format="json")
    PosicionEnVivo.objects.update(actualizado_en=timezone.now() - timedelta(minutes=5))
    assert api_admin.get(URL_EN_VIVO).json() == []


def test_al_cerrar_sesion_desaparece_del_mapa(client, conductor, api_admin):
    client.post(
        "/ingresar/", {"email": conductor.usuario.email, "password": CLAVE, "acepta_datos": "on"}
    )
    # Con la cookie JWT de la web (como lo hace static/js/conductor.js).
    r = client.post(
        URL_POSICION, {"latitud": "1.2", "longitud": "-77.2"}, content_type="application/json"
    )
    assert r.status_code == 204
    assert len(api_admin.get(URL_EN_VIVO).json()) == 1

    client.post("/salir/")
    assert api_admin.get(URL_EN_VIVO).json() == []


def test_api_logout_tambien_desconecta(api_conductor, api_admin, conductor):
    api_conductor.post(URL_POSICION, {"latitud": "1.2", "longitud": "-77.2"}, format="json")
    refresh = emitir_tokens(conductor.usuario)["refresh"]
    assert (
        api_conductor.post("/api/auth/logout/", {"refresh": refresh}, format="json").status_code
        == 204
    )
    assert api_admin.get(URL_EN_VIVO).json() == []


def test_pagina_del_conductor_exige_rol(web_admin, client):
    r = web_admin.get("/conductor/", follow=True)
    assert r.redirect_chain[-1][0] == "/panel/"


def test_pagina_del_conductor_sin_sesion_pide_ingresar(client, db):
    r = client.get("/conductor/")
    assert r.status_code == 302 and r.url.startswith("/ingresar/")


def test_panel_hoy_incluye_capa_en_vivo(web_admin):
    contenido = web_admin.get("/panel/").content.decode()
    assert 'data-vivo="' + URL_EN_VIVO + '"' in contenido
    assert "maplibre-gl" in contenido


def test_conductor_creado_por_el_admin_puede_ingresar(api_admin, client):
    r = api_admin.post(
        "/api/conductores/",
        {
            "email": "nuevo.conductor@test.co",
            "first_name": "Nuevo",
            "last_name": "Conductor",
            "password": "Clave-Nueva-2026",
            "tipo_documento": "CC",
            "numero_documento": "5555",
            "telefono": "3005555555",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    r = client.post(
        "/ingresar/",
        {"email": "nuevo.conductor@test.co", "password": "Clave-Nueva-2026", "acepta_datos": "on"},
    )
    assert r.status_code == 302 and r["Location"] == "/conductor/"
    assert settings.JWT_COOKIE_ACCESS in r.cookies
