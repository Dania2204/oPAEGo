"""Configuración de pruebas.

Por defecto usa SQLite en memoria para que `pytest` corra sin Docker; con
TEST_DATABASE_URL se puede apuntar a PostgreSQL (recomendado en CI).
"""

from .base import *  # noqa: F403

DATABASES = {
    "default": env.db("TEST_DATABASE_URL", default="sqlite://:memory:")  # noqa: F405
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = BASE_DIR / ".media-test"  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Clave Fernet fija solo para pruebas.
BIOMETRIA_CLAVE = "x2YUvpS3yZb8OyFfHHk3J2CL9w4_8oZy9pDmH5lyGJE="
