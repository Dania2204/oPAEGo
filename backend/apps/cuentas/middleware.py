"""Resuelve `request.user` a partir del JWT guardado en cookie (web).

Reemplaza a SessionMiddleware/AuthenticationMiddleware: la plataforma web
usa el mismo mecanismo de autenticación que la API (JWT, RNF-08).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

from .tokens import borrar_cookies, poner_cookies, renovar_desde_refresh


class JWTCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tokens_nuevos = None
        borrar = False
        request.user = AnonymousUser()

        if "HTTP_AUTHORIZATION" not in request.META:
            access = request.COOKIES.get(settings.JWT_COOKIE_ACCESS)
            refresh = request.COOKIES.get(settings.JWT_COOKIE_REFRESH)
            usuario = self._usuario_desde_access(access) if access else None
            if usuario is None and refresh:
                renovado = renovar_desde_refresh(refresh)
                if renovado:
                    usuario, tokens_nuevos = renovado
                    # Para que la autenticación de DRF vea el token vigente.
                    request.COOKIES[settings.JWT_COOKIE_ACCESS] = tokens_nuevos["access"]
                else:
                    borrar = True
            elif usuario is None and access:
                borrar = True
            if usuario is not None:
                request.user = usuario

        respuesta = self.get_response(request)
        if getattr(request, "_jwt_cierre_sesion", False):
            return respuesta
        if tokens_nuevos:
            poner_cookies(respuesta, tokens_nuevos)
        elif borrar:
            borrar_cookies(respuesta)
        return respuesta

    @staticmethod
    def _usuario_desde_access(access):
        try:
            token = AccessToken(access)
        except TokenError:
            return None
        usuario_id = token.get(api_settings.USER_ID_CLAIM)
        return get_user_model().objects.filter(pk=usuario_id, is_active=True).first()
