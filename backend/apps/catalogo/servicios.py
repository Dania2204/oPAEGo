"""Altas, ediciones y desactivaciones del catálogo con auditoría (RF-04 a RF-12)."""

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.cuentas.models import Rol
from apps.envios.servicios import normalizar_ocurrido_en


def _exigir_admin(usuario):
    if usuario.rol != Rol.ADMINISTRADOR:
        raise PermissionDenied("Solo el administrador gestiona el catálogo.")


@transaction.atomic
def guardar(usuario, serializer_class, datos, *, instancia=None, ocurrido_en=None, request=None):
    """Valida con el serializer de la API y registra la auditoría."""
    _exigir_admin(usuario)
    serializer = serializer_class(instance=instancia, data=datos, partial=instancia is not None)
    serializer.is_valid(raise_exception=True)
    objeto = serializer.save()
    datos_auditoria = {k: v for k, v in serializer.validated_data.items() if k != "password"}
    registrar(
        usuario,
        Accion.EDITAR if instancia is not None else Accion.CREAR,
        f"{objeto._meta.verbose_name.capitalize()}: {objeto}",
        objeto=objeto,
        ocurrido_en=normalizar_ocurrido_en(ocurrido_en),
        request=request,
        datos={"campos": sorted(str(k) for k in datos_auditoria)},
    )
    return objeto


@transaction.atomic
def cambiar_activo(usuario, objeto, activo, *, ocurrido_en=None, request=None):
    """RF-04, RF-08, RF-10: desactivar (o reactivar) sin borrar el historial."""
    _exigir_admin(usuario)
    from django.contrib.auth import get_user_model

    if isinstance(objeto, get_user_model()):
        if objeto.pk == usuario.pk and not activo:
            raise PermissionDenied("No puede desactivar su propio usuario.")
        objeto.is_active = activo
        objeto.save(update_fields=["is_active"])
        for perfil in ("conductor", "responsable_recepcion"):
            relacionado = getattr(objeto, perfil, None)
            if relacionado is not None:
                relacionado.activo = activo
                relacionado.save(update_fields=["activo"])
    else:
        objeto.activo = activo
        objeto.save(update_fields=["activo", "actualizado_en"])
        usuario_asociado = getattr(objeto, "usuario", None)
        if usuario_asociado is not None:
            usuario_asociado.is_active = activo
            usuario_asociado.save(update_fields=["is_active"])
    registrar(
        usuario,
        Accion.ACTIVAR if activo else Accion.DESACTIVAR,
        f"{objeto._meta.verbose_name.capitalize()}: {objeto}",
        objeto=objeto,
        ocurrido_en=normalizar_ocurrido_en(ocurrido_en),
        request=request,
    )
    return objeto
