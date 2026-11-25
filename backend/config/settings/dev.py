from .base import *  # noqa: F403

DEBUG = env.bool("DJANGO_DEBUG", default=True)  # noqa: F405

# Que el navegador no reutilice JS/CSS viejos entre cambios (ver config/estaticos_dev.py).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "config.estaticos_dev.EstaticosVersionados"},
}
