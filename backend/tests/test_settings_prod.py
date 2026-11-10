"""Configuración de producción en Azure App Service (config/settings/prod.py)."""

import importlib
import sys

import pytest


@pytest.fixture
def cargar_prod(monkeypatch):
    def cargar(**variables):
        monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 60)
        for nombre, valor in variables.items():
            monkeypatch.setenv(nombre, valor)
        for modulo in ("config.settings.prod", "config.settings.base"):
            sys.modules.pop(modulo, None)
        return importlib.import_module("config.settings.prod")

    yield cargar
    for modulo in ("config.settings.prod", "config.settings.base"):
        sys.modules.pop(modulo, None)


def test_acepta_el_dominio_de_azure(cargar_prod):
    prod = cargar_prod(
        DJANGO_ALLOWED_HOSTS="paego.example.co",
        WEBSITE_HOSTNAME="azwaabc.azurewebsites.net",
    )
    assert prod.ALLOWED_HOSTS == ["paego.example.co", "azwaabc.azurewebsites.net"]
    assert "https://azwaabc.azurewebsites.net" in prod.CSRF_TRUSTED_ORIGINS


def test_media_root_configurable(cargar_prod, tmp_path):
    prod = cargar_prod(MEDIA_ROOT=str(tmp_path / "media"))
    assert prod.MEDIA_ROOT == tmp_path / "media"
