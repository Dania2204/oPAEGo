"""Emisión y revocación de los JWT de PAEGo (RF-01, RF-02, RNF-08)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken


def emitir_tokens(usuario):
    refresh = RefreshToken.for_user(usuario)
    refresh["rol"] = usuario.rol
    refresh["nombre"] = usuario.get_full_name()
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


def renovar_desde_refresh(refresh_str):
    """Emite un par nuevo a partir de un refresh vigente y no revocado.

    Lo usa el navegador cuando el access token expira. No se revoca el refresh
    anterior para que peticiones simultáneas no cierren la sesión; ese token
    vence solo en JWT_INACTIVIDAD_MIN. Devuelve (usuario, tokens) o None.
    """
    try:
        refresh = RefreshToken(refresh_str)  # valida firma, vencimiento y lista negra
    except TokenError:
        return None
    usuario_id = refresh.get(api_settings.USER_ID_CLAIM)
    usuario = get_user_model().objects.filter(pk=usuario_id, is_active=True).first()
    if usuario is None:
        return None
    return usuario, emitir_tokens(usuario)


def revocar_refresh(refresh_str):
    if not refresh_str:
        return
    try:
        RefreshToken(refresh_str).blacklist()
    except TokenError:
        pass


def poner_cookies(respuesta, tokens):
    opciones = {
        "httponly": True,
        "secure": settings.JWT_COOKIE_SECURE,
        "samesite": "Lax",
        "path": "/",
    }
    respuesta.set_cookie(
        settings.JWT_COOKIE_ACCESS,
        tokens["access"],
        max_age=settings.JWT_ACCESS_MIN * 60,
        **opciones,
    )
    respuesta.set_cookie(
        settings.JWT_COOKIE_REFRESH,
        tokens["refresh"],
        max_age=settings.JWT_INACTIVIDAD_MIN * 60,
        **opciones,
    )


def borrar_cookies(respuesta):
    respuesta.delete_cookie(settings.JWT_COOKIE_ACCESS, path="/")
    respuesta.delete_cookie(settings.JWT_COOKIE_REFRESH, path="/")
