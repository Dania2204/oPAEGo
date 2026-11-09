from django.conf import settings

from apps.cuentas.models import Rol

from .consultas import alertas_retraso, novedades_sin_leer


def notificaciones(request):
    """Datos comunes del panel: entidad (cabecera GOV.CO) y contadores de
    alertas (RF-30) y novedades sin atender (RF-31) para la navegación."""
    contexto = {"paego": settings.PAEGO}
    usuario = getattr(request, "user", None)
    if usuario and usuario.is_authenticated and usuario.rol == Rol.ADMINISTRADOR:
        contexto["novedades_pendientes"] = novedades_sin_leer().count()
        contexto["alertas_pendientes"] = alertas_retraso().count()
    return contexto
