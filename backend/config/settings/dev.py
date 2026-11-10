from .base import *  # noqa: F403

DEBUG = env.bool("DJANGO_DEBUG", default=True)  # noqa: F405

# Desarrollo: clave de biometría derivada de SECRET_KEY si no se define otra.
if not BIOMETRIA_CLAVE:  # noqa: F405
    import base64
    import hashlib

    BIOMETRIA_CLAVE = base64.urlsafe_b64encode(
        hashlib.sha256(("biometria:" + SECRET_KEY).encode()).digest()  # noqa: F405
    ).decode()
