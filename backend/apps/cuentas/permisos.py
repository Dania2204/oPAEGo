"""Permisos por rol con mínimo privilegio (RF-06, RNF-07)."""

from django.contrib.auth.mixins import AccessMixin
from rest_framework.permissions import BasePermission

from .models import Rol


class _PorRol(BasePermission):
    roles: tuple = ()
    message = "Su rol no tiene permiso para realizar esta acción."

    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and usuario.rol in self.roles)


class EsAdministrador(_PorRol):
    roles = (Rol.ADMINISTRADOR,)


class EsConductor(_PorRol):
    roles = (Rol.CONDUCTOR,)


class EsInstitucion(_PorRol):
    roles = (Rol.INSTITUCION,)


class EsSupervisor(_PorRol):
    roles = (Rol.SUPERVISOR,)


class EsSupervisorOAdministrador(_PorRol):
    roles = (Rol.SUPERVISOR, Rol.ADMINISTRADOR)


class EsConductorOInstitucion(_PorRol):
    roles = (Rol.CONDUCTOR, Rol.INSTITUCION)


class AdministradorRequeridoMixin(AccessMixin):
    """Vistas web: solo el administrador usa la plataforma web (numeral 3.2.3)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.rol != Rol.ADMINISTRADOR:
            from django.shortcuts import render

            return render(request, "cuentas/sin_acceso_web.html", status=403)
        return super().dispatch(request, *args, **kwargs)
