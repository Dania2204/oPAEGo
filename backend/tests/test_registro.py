"""Registros en JSON y Sentry opcional (config/registro.py)."""

import json
import logging
import logging.config
import sys

from config.registro import FormatoJson, activar_sentry, configuracion


def test_formato_json_una_linea_con_extras():
    registro = logging.LogRecord(
        "apps.envios", logging.WARNING, __file__, 1, "Envío %s demorado", ("PAE-1",), None
    )
    registro.envio_id = 7
    linea = FormatoJson().format(registro)

    assert "\n" not in linea
    datos = json.loads(linea)
    assert datos["nivel"] == "WARNING"
    assert datos["logger"] == "apps.envios"
    assert datos["mensaje"] == "Envío PAE-1 demorado"
    assert datos["envio_id"] == 7
    assert datos["hora"].endswith("+00:00")
    assert "excepcion" not in datos


def test_formato_json_incluye_la_traza():
    try:
        raise ValueError("falló")
    except ValueError:
        registro = logging.LogRecord(
            "apps", logging.ERROR, __file__, 1, "Error", (), sys.exc_info()
        )
    datos = json.loads(FormatoJson().format(registro))
    assert "ValueError: falló" in datos["excepcion"]


def test_configuracion_valida_para_dictconfig():
    config = configuracion("json", "DEBUG")
    logging.config.dictConfig(config)
    assert config["handlers"]["consola"]["formatter"] == "json"
    assert logging.getLogger("apps").level == logging.DEBUG
    logging.config.dictConfig(configuracion())


def test_sentry_solo_con_dsn(monkeypatch):
    assert activar_sentry("", "pruebas") is False

    llamadas = {}
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: llamadas.update(kw))
    assert activar_sentry("https://clave@o0.ingest.sentry.io/0", "pruebas") is True
    assert llamadas["environment"] == "pruebas"
    assert llamadas["send_default_pii"] is False
