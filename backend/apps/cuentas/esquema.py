"""Documentación OpenAPI (RNF-19): la autenticación de PAEGo es JWT Bearer.

Sin esta extensión Swagger no sabe cómo autenticar y no ofrece el botón
«Authorize» al equipo de la aplicación móvil.
"""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class CookieJWTScheme(SimpleJWTScheme):
    target_class = "apps.cuentas.autenticacion.CookieJWTAuthentication"
    name = "jwtAuth"
