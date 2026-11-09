"""Cliente mínimo de la API de Gemini (Google AI) para el asistente de
nutrición de la app móvil. La clave vive solo en el servidor (GEMINI_API_KEY):
así no viaja dentro del APK."""

import json
import logging
import urllib.error
import urllib.request
from urllib.parse import quote

from django.conf import settings

logger = logging.getLogger(__name__)

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


class GeminiNoConfigurado(Exception):
    """No hay GEMINI_API_KEY en el servidor."""


class GeminiError(Exception):
    """Gemini no respondió o respondió algo inutilizable."""


def configurado():
    return bool(settings.GEMINI_API_KEY)


def generar(instrucciones, mensajes):
    """Pide a Gemini la siguiente respuesta de la conversación.

    `mensajes` es una lista de (rol, texto) con rol "user" o "model".
    Devuelve el texto de la respuesta.
    """
    if not configurado():
        raise GeminiNoConfigurado
    cuerpo = {
        "systemInstruction": {"parts": [{"text": instrucciones}]},
        "contents": [{"role": rol, "parts": [{"text": texto}]} for rol, texto in mensajes],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }
    peticion = urllib.request.Request(
        URL.format(modelo=quote(settings.GEMINI_MODEL, safe="-._")),
        data=json.dumps(cuerpo).encode(),
        headers={
            "Content-Type": "application/json",
            # En la cabecera y no en la URL: así no queda en registros de proxies.
            "x-goog-api-key": settings.GEMINI_API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=settings.GEMINI_TIMEOUT_SEG) as r:
            datos = json.loads(r.read())
    except urllib.error.HTTPError as e:
        logger.warning("Gemini respondió %s", e.code)
        raise GeminiError from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        logger.warning("No se pudo consultar Gemini: %s", e)
        raise GeminiError from e

    candidatos = datos.get("candidates") or []
    partes = ((candidatos[0].get("content") or {}).get("parts") or []) if candidatos else []
    texto = "".join(str(p.get("text", "")) for p in partes if isinstance(p, dict)).strip()
    if not texto:
        raise GeminiError("respuesta vacía")
    return texto
