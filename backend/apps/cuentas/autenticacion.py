"""Autenticación JWT para la API: encabezado Bearer (app móvil) o cookie (web)."""

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication


class _VerificadorCSRF(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


class CookieJWTAuthentication(JWTAuthentication):
    """Primero busca `Authorization: Bearer`; si no, la cookie httpOnly.

    Cuando el token viene en cookie (navegador) se exige CSRF en los métodos
    que modifican datos, igual que SessionAuthentication de DRF.
    """

    def authenticate(self, request):
        encabezado = self.get_header(request)
        if encabezado is not None:
            return super().authenticate(request)

        crudo = request.COOKIES.get(settings.JWT_COOKIE_ACCESS)
        if not crudo:
            return None
        token_validado = self.get_validated_token(crudo)
        usuario = self.get_user(token_validado)
        self._exigir_csrf(request)
        return usuario, token_validado

    def _exigir_csrf(self, request):
        def respuesta_dummy(req):
            return None

        verificador = _VerificadorCSRF(respuesta_dummy)
        verificador.process_request(request)
        motivo = verificador.process_view(request, None, (), {})
        if motivo:
            raise exceptions.PermissionDenied(f"CSRF fallido: {motivo}")
