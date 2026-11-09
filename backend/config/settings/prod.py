"""Configuración de producción (servidor asignado por la Secretaría de Educación).

RNF-10: toda la comunicación debe ir por HTTPS.
"""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")  # noqa: F405 — obligatoria en producción

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
CSRF_COOKIE_SECURE = True
JWT_COOKIE_SECURE = True

# La documentación de la API solo para usuarios autenticados.
SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,  # noqa: F405
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}

# Archivos estáticos con hash en el nombre: cada versión tiene URL nueva, así la
# caché del navegador y del service worker (PWA, RF-38) nunca sirve JS o CSS viejos.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# WhiteNoise sirve los estáticos desde la misma aplicación (sin Nginx aparte).
MIDDLEWARE = [
    MIDDLEWARE[0],  # noqa: F405 — SecurityMiddleware va primero
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],  # noqa: F405
]

# Dominios desde los que se aceptan formularios (p. ej. https://paego.up.railway.app).
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405
