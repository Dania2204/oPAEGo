"""La IP de auditoría tolera el formato de los proxies (p. ej. Azure: `ip:puerto`)."""

import pytest
from django.test import RequestFactory

from apps.auditoria.servicios import _ip


@pytest.mark.parametrize(
    ("reenviada", "esperada"),
    [
        ("200.1.2.3:56789", "200.1.2.3"),  # Azure App Service
        ("200.1.2.3:56789, 10.0.0.1", "200.1.2.3"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("2001:db8::1", "2001:db8::1"),
        ("200.1.2.3", "200.1.2.3"),
        ("basura", "127.0.0.1"),  # cabecera falsa → REMOTE_ADDR
    ],
)
def test_ip_desde_x_forwarded_for(reenviada, esperada):
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR=reenviada)
    assert _ip(request) == esperada


def test_ip_sin_cabecera_usa_remote_addr():
    assert _ip(RequestFactory().get("/", REMOTE_ADDR="10.1.1.1")) == "10.1.1.1"


def test_ip_invalida_en_todo_es_none():
    assert _ip(RequestFactory().get("/", REMOTE_ADDR="x")) is None


@pytest.mark.django_db
def test_login_api_con_cabecera_de_azure():
    from rest_framework.test import APIClient

    from apps.cuentas.models import Usuario

    Usuario.objects.create_user(
        email="a@paego.local", password="Clave-Segura-123", rol="ADMINISTRADOR"
    )
    r = APIClient().post(
        "/api/auth/token/",
        {"email": "a@paego.local", "password": "Clave-Segura-123"},
        format="json",
        HTTP_X_FORWARDED_FOR="200.1.2.3:56789",
    )
    assert r.status_code == 200
