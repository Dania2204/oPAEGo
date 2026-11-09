"""Límite de intentos por IP contra la fuerza bruta (apps/cuentas/limite.py)."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from .conftest import CLAVE


@pytest.fixture
def tasas(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"login": "3/min", "renovar": "3/min", "restablecer": "2/hour"},
    }


def _login_api(cliente, email, password):
    return cliente.post(reverse("api:token"), {"email": email, "password": password}, format="json")


def test_api_login_bloquea_tras_superar_el_limite(tasas, admin):
    cliente = APIClient()
    for _ in range(3):
        assert _login_api(cliente, admin.email, "mala").status_code == 401
    respuesta = _login_api(cliente, admin.email, CLAVE)
    assert respuesta.status_code == 429
    assert "Retry-After" in respuesta.headers


def test_api_login_el_limite_es_por_ip(tasas, admin):
    for _ in range(3):
        _login_api(APIClient(REMOTE_ADDR="10.0.0.1"), admin.email, "mala")
    otra_ip = APIClient(REMOTE_ADDR="10.0.0.2")
    assert _login_api(otra_ip, admin.email, CLAVE).status_code == 200


def test_api_renovar_token_tiene_limite(tasas):
    cliente = APIClient()
    url = reverse("api:token_refresh")
    for _ in range(3):
        assert cliente.post(url, {"refresh": "x"}, format="json").status_code == 401
    assert cliente.post(url, {"refresh": "x"}, format="json").status_code == 429


def test_api_restablecer_tiene_limite(tasas, admin):
    cliente = APIClient()
    url = reverse("api:restablecer")
    for _ in range(2):
        assert cliente.post(url, {"email": admin.email}, format="json").status_code == 202
    assert cliente.post(url, {"email": admin.email}, format="json").status_code == 429


def test_panel_login_bloquea_y_muestra_mensaje(tasas, client, admin):
    url = reverse("cuentas:login")
    for _ in range(3):
        client.post(url, {"email": admin.email, "password": "mala"})
    respuesta = client.post(url, {"email": admin.email, "password": CLAVE, "acepta_datos": "on"})
    assert respuesta.status_code == 429
    assert "Demasiados intentos" in respuesta.content.decode()
    assert "paego_access" not in respuesta.cookies
