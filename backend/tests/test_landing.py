"""Página pública (landing) en `/`."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import cache

from apps.cuentas.tokens import emitir_tokens, poner_cookies
from apps.monitoreo import cifras_publicas

pytestmark = pytest.mark.django_db

PLANTILLA = Path(settings.BASE_DIR) / "templates" / "publico" / "landing.html"


def test_visitante_ve_la_landing(client, institucion):
    r = client.get("/")
    assert r.status_code == 200
    html = r.content.decode()
    assert "Cada ración del PAE" in html
    assert 'href="/ingresar/"' in html
    assert 'data-cifra="1"' in html  # una institución activa
    assert "Política de tratamiento de datos" in html


def test_con_sesion_va_al_panel(web_admin):
    r = web_admin.get("/")
    assert r.status_code == 302 and r["Location"] == "/panel/"


def test_rol_sin_web_va_al_ingreso(client, supervisor):
    poner_cookies_cliente(client, supervisor)
    r = client.get("/")
    assert r.status_code == 302 and r["Location"] == "/ingresar/"


def poner_cookies_cliente(client, usuario):
    class _R(dict):
        def set_cookie(self, clave, valor, **kwargs):
            self[clave] = valor

    cookies = _R()
    poner_cookies(cookies, emitir_tokens(usuario))
    for clave, valor in cookies.items():
        client.cookies[clave] = valor


def test_video_principal_pendiente_muestra_poster(client, settings):
    settings.PAEGO = {**settings.PAEGO, "VIDEO_PRINCIPAL_URL": ""}
    html = client.get("/").content.decode()
    assert "próximamente" in html
    assert "<video controls" not in html


def test_video_principal_configurado(client, settings):
    settings.PAEGO = {
        **settings.PAEGO,
        "VIDEO_PRINCIPAL_URL": "/static/video/landing/presentacion.mp4",
    }
    html = client.get("/").content.decode()
    assert "<video controls" in html
    assert "/static/video/landing/presentacion.mp4" in html
    assert "próximamente" not in html


def test_cifras_son_agregadas_y_se_cachean(institucion, django_assert_num_queries):
    cache.clear()
    with django_assert_num_queries(4):
        datos = cifras_publicas.cifras()
    assert set(datos) == {"instituciones", "estudiantes", "envios", "entregas"}
    assert all(isinstance(v, int) for v in datos.values())
    with django_assert_num_queries(0):
        cifras_publicas.cifras()


def test_qr_de_ejemplo_no_es_de_un_estudiante():
    svg = cifras_publicas.qr_de_ejemplo()
    assert svg.startswith("<svg") and "un estudiante de ejemplo" in svg


def test_todos_los_estaticos_de_la_landing_existen():
    # En producción (ManifestStaticFilesStorage) un {% static %} inexistente da error 500.
    texto = PLANTILLA.read_text(encoding="utf-8") + (
        Path(settings.BASE_DIR) / "templates" / "base_publico.html"
    ).read_text(encoding="utf-8")
    rutas = set(re.findall(r"\{% static '([^']+)' %\}", texto))
    assert rutas
    faltan = sorted(r for r in rutas if not finders.find(r))
    assert not faltan, f"Faltan estáticos: {faltan}"
