"""Registros (logs) de la aplicación y monitoreo de errores con Sentry.

En producción los registros salen por la consola en JSON, una línea por evento,
para que Railway (o cualquier recolector) los pueda filtrar por campo. Sentry
es opcional: solo se activa con la variable SENTRY_DSN.
"""

import json
import logging
from datetime import UTC, datetime

# Atributos estándar de LogRecord: todo lo demás llegó por `extra=` y se incluye.
_ESTANDAR = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class FormatoJson(logging.Formatter):
    """Una línea JSON por registro: hora UTC, nivel, logger, mensaje, extras
    y la traza si hubo excepción."""

    def format(self, record):
        datos = {
            "hora": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "mensaje": record.getMessage(),
        }
        for clave, valor in vars(record).items():
            if clave not in _ESTANDAR and not clave.startswith("_"):
                datos[clave] = valor
        if record.exc_info:
            datos["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False, default=str)


def configuracion(formato="texto", nivel="INFO"):
    """Diccionario para `settings.LOGGING`."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": FormatoJson},
            "texto": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
        },
        "handlers": {
            "consola": {"class": "logging.StreamHandler", "formatter": formato},
        },
        "root": {"handlers": ["consola"], "level": nivel},
        "loggers": {
            # Errores 5xx con su traza y avisos 4xx de Django.
            "django": {"level": "WARNING", "propagate": True},
            "apps": {"level": nivel, "propagate": True},
        },
    }


def activar_sentry(dsn, entorno, muestreo_trazas=0.0):
    """Envía los errores no controlados a Sentry. Sin datos personales:
    PAEGo maneja datos de menores y de funcionarios (Ley 1581 de 2012)."""
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=entorno,
        send_default_pii=False,
        traces_sample_rate=muestreo_trazas,
    )
    return True
