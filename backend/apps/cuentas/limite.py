"""Límite de intentos por IP para el inicio de sesión, la renovación del token
y el restablecimiento de contraseña (contra la fuerza bruta).

Las tasas están en `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` (variables
LIMITE_*). La API usa `LimitePorAlcance` con `throttle_scope`; las vistas HTML
del panel usan `permitido()`, que comparte el mismo contador por IP.
"""

from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class _TasasVigentes:
    # DRF copia las tasas en un atributo de clase al importar; leerlas en cada
    # petición respeta los cambios de configuración (y los de las pruebas).
    @property
    def THROTTLE_RATES(self):  # noqa: N802 (nombre que espera DRF)
        return api_settings.DEFAULT_THROTTLE_RATES


class LimitePorAlcance(_TasasVigentes, ScopedRateThrottle):
    """Para vistas de la API con `throttle_scope`. Responde 429 con Retry-After."""


class _LimitePorIp(_TasasVigentes, SimpleRateThrottle):
    def __init__(self, alcance):
        self.scope = alcance
        super().__init__()

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def permitido(request, alcance):
    """Registra un intento y dice si todavía está dentro del límite."""
    return _LimitePorIp(alcance).allow_request(request, None)
