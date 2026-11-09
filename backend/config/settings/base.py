"""Configuración base de PAEGo (plataforma web: Django + DRF + JWT)."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="cambiar-esta-clave-en-produccion")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "apps.cuentas",
    "apps.catalogo",
    "apps.envios",
    "apps.auditoria",
    "apps.monitoreo",
    "apps.sincronizacion",
    "apps.nutricion",
]

# No se usan sesiones de Django: la autenticación de la web y de la API es
# JWT (RF-01, RNF-08). El usuario se resuelve con JWTCookieMiddleware.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "apps.cuentas.middleware.JWTCookieMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Los servidores de teselas del mapa exigen conocer el origen (Referer) de la
# petición; con "same-origin" el navegador no lo envía y pueden bloquear el mapa.
# Solo se comparte el dominio, nunca la ruta ni los parámetros.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.monitoreo.context_processors.notificaciones",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# RNF-17: el modelo de datos se define con el ORM de Django; el motor se
# cambia solo con DATABASE_URL (PostgreSQL recomendado, numeral 2.2.5.2).
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://pae_user:pae_password@localhost:5434/pae_go",
    )
}

AUTH_USER_MODEL = "cuentas.Usuario"

# RNF-09: contraseñas con hash (PBKDF2 por defecto de Django).
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

LOGIN_URL = "cuentas:login"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.cuentas.autenticacion.CookieJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Intentos por IP (apps/cuentas/limite.py). Al superarlos la API responde 429.
    "DEFAULT_THROTTLE_RATES": {
        "login": env("LIMITE_LOGIN", default="10/min"),
        "renovar": env("LIMITE_RENOVAR", default="30/min"),
        "restablecer": env("LIMITE_RESTABLECER", default="5/hour"),
        # Consultas al asistente de nutrición, por usuario (gastan cuota de Gemini).
        "nutricion": env("LIMITE_NUTRICION", default="20/hour"),
    },
}

# Caché de los contadores de intentos. Por defecto en memoria de cada proceso;
# con varios workers de gunicorn conviene una compartida, p. ej.
# CACHE_URL=dbcache://cache_paego (y `manage.py createcachetable`) o rediscache://.
CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

# Asistente de nutrición de la app móvil (apps/nutricion). Sin clave responde 503.
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL", default="gemini-2.5-flash")
GEMINI_TIMEOUT_SEG = env.int("GEMINI_TIMEOUT_SEG", default=30)

# RF-02 / RNF-08: el access token dura poco y el refresh rota en cada uso.
# Si el usuario pasa JWT_INACTIVIDAD_MIN minutos sin actividad, el refresh
# vence y la sesión expira automáticamente.
JWT_ACCESS_MIN = env.int("JWT_ACCESS_MIN", default=10)
JWT_INACTIVIDAD_MIN = env.int("JWT_INACTIVIDAD_MIN", default=30)
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=JWT_ACCESS_MIN),
    "REFRESH_TOKEN_LIFETIME": timedelta(minutes=JWT_INACTIVIDAD_MIN),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}
JWT_COOKIE_ACCESS = "paego_access"
JWT_COOKIE_REFRESH = "paego_refresh"
JWT_COOKIE_SECURE = env.bool("JWT_COOKIE_SECURE", default=False)

SPECTACULAR_SETTINGS = {
    "TITLE": "PAEGo API",
    "DESCRIPTION": (
        "API REST de PAEGo — Sistema integral de gestión y monitoreo del PAE. "
        "La consumen la plataforma web (administrador) y la aplicación móvil "
        "Flutter (conductor e institución educativa). Autenticación JWT."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "TipoNovedadEnum": "apps.envios.models.Novedad.Tipo",
        "TipoOperacionEnum": "apps.sincronizacion.operaciones.OPERACIONES",
    },
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-responder@paego.local")
URL_PUBLICA = env("URL_PUBLICA", default="http://localhost:8000")

# Reglas de negocio configurables.
PAEGO = {
    # Entidad administradora que aparece en la cabecera (GOV.CO).
    "ENTIDAD": env("PAEGO_ENTIDAD", default="Alcaldía de Pasto"),
    "DEPENDENCIA": env("PAEGO_DEPENDENCIA", default="Secretaría de Educación Municipal"),
    # RF-30 / indicador "a tiempo": minutos de tolerancia sobre la hora programada.
    "TOLERANCIA_ENTREGA_MIN": env.int("PAEGO_TOLERANCIA_ENTREGA_MIN", default=30),
    # RNF-02: intervalo sugerido de envío de ubicación (lo usa el cliente móvil).
    "INTERVALO_UBICACION_SEG": env.int("PAEGO_INTERVALO_UBICACION_SEG", default=15),
    # RF-29: refresco del mapa del administrador.
    "INTERVALO_MAPA_SEG": env.int("PAEGO_INTERVALO_MAPA_SEG", default=10),
    # RF-38: diferencia a partir de la cual un registro se marca como diferido.
    "UMBRAL_DIFERIDO_MIN": env.int("PAEGO_UMBRAL_DIFERIDO_MIN", default=5),
    # RF-38: tolerancia al reloj adelantado del dispositivo.
    "TOLERANCIA_RELOJ_MIN": env.int("PAEGO_TOLERANCIA_RELOJ_MIN", default=5),
}

# Registros por consola (config/registro.py). LOG_FORMATO=json en producción.
from config.registro import configuracion as _registro  # noqa: E402

LOGGING = _registro(env("LOG_FORMATO", default="texto"), env("LOG_NIVEL", default="INFO"))
