"""Reglas de la entrega del PAE a estudiantes (rol SUPERVISOR).

API, panel web y sincronización sin conexión pasan por estas funciones: permisos
por institución, verificación del código QR y auditoría se aplican siempre igual.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.cuentas.models import Rol
from apps.envios.servicios import normalizar_ocurrido_en

from .models import (
    PREFIJO_QR,
    EntregaEstudiante,
    Estudiante,
    MetodoEntrega,
    Supervisor,
    nuevo_codigo_qr,
)


# --------------------------------------------------------------------------
# Acceso por institución
# --------------------------------------------------------------------------
def institucion_de(usuario, *, lectura=False):
    """Institución del usuario; None si es administrador (ve todas).

    Con `lectura=True` también se admite el responsable de la institución (solo
    consulta: la app de la institución muestra quién recibió hoy).
    """
    if usuario.rol == Rol.ADMINISTRADOR:
        return None
    if usuario.rol == Rol.SUPERVISOR:
        supervisor = (
            Supervisor.objects.filter(usuario=usuario, activo=True)
            .select_related("institucion")
            .first()
        )
        if supervisor is None:
            raise PermissionDenied("Su usuario no tiene una institución asignada como supervisor.")
        return supervisor.institucion
    if lectura and usuario.rol == Rol.INSTITUCION:
        responsable = getattr(usuario, "responsable_recepcion", None)
        if responsable is not None and responsable.activo:
            return responsable.institucion
    raise PermissionDenied("Su rol no tiene permiso para realizar esta acción.")


def estudiantes_visibles(usuario, *, lectura=False):
    institucion = institucion_de(usuario, lectura=lectura)
    qs = Estudiante.objects.select_related("institucion")
    return qs if institucion is None else qs.filter(institucion=institucion)


def _exigir_acceso(usuario, estudiante):
    institucion = institucion_de(usuario)
    if institucion is not None and estudiante.institucion_id != institucion.pk:
        raise PermissionDenied("El estudiante no pertenece a su institución.")
    if not estudiante.activo:
        raise ValidationError({"estudiante": "El estudiante no está activo en la matrícula."})


def dar_de_baja(estudiante, *, usuario=None):
    """El estudiante salió de la matrícula: queda inactivo y su QR deja de servir."""
    if estudiante.activo:
        estudiante.activo = False
        estudiante.save(update_fields=["activo", "actualizado_en"])


# --------------------------------------------------------------------------
# Código QR
# --------------------------------------------------------------------------
def codigo_de(texto):
    """Código del estudiante a partir del texto leído (con o sin el prefijo)."""
    texto = (texto or "").strip()
    if texto.startswith(PREFIJO_QR):
        texto = texto[len(PREFIJO_QR) :]
    return texto


@transaction.atomic
def regenerar_qr(usuario, estudiante, *, request=None):
    """Carné perdido o expuesto: nuevo código; el anterior deja de servir."""
    if usuario.rol != Rol.ADMINISTRADOR:
        raise PermissionDenied("Solo el administrador regenera el código QR.")
    estudiante.codigo_qr = nuevo_codigo_qr()
    estudiante.save(update_fields=["codigo_qr", "actualizado_en"])
    registrar(
        usuario,
        Accion.QR_REGENERADO,
        f"Se regeneró el código QR de {estudiante.nombre_completo}.",
        objeto=estudiante,
        request=request,
    )
    return estudiante.codigo_qr


# --------------------------------------------------------------------------
# Entrega diaria
# --------------------------------------------------------------------------
def registrar_entrega(
    usuario,
    estudiante,
    *,
    metodo,
    fecha=None,
    codigo="",
    motivo="",
    ocurrido_en=None,
    request=None,
):
    """El estudiante recibió el PAE. Una sola vez por día; con su QR o manual."""
    if usuario.rol not in (Rol.SUPERVISOR, Rol.ADMINISTRADOR):
        raise PermissionDenied("Solo el supervisor registra entregas a estudiantes.")
    _exigir_acceso(usuario, estudiante)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    fecha = fecha or timezone.localdate(ocurrido_en)
    motivo = (motivo or "").strip()

    if metodo == MetodoEntrega.QR:
        leido = codigo_de(codigo)
        if not leido:
            raise ValidationError({"codigo": "Falta el código QR leído."})
        if not secrets.compare_digest(leido, estudiante.codigo_qr):
            raise ValidationError(
                {"codigo": "El código QR no corresponde a este estudiante."}, code="qr_invalido"
            )
    elif metodo == MetodoEntrega.MANUAL:
        if not motivo:
            raise ValidationError({"motivo": "Indique por qué se registra sin el código QR."})
    else:
        raise ValidationError({"metodo": "Método de entrega no válido."})

    if EntregaEstudiante.objects.filter(estudiante=estudiante, fecha=fecha).exists():
        raise ValidationError(
            {"estudiante": f"{estudiante.nombre_completo} ya recibió el PAE ese día."},
            code="duplicada",
        )
    umbral_diferido = timedelta(minutes=settings.PAEGO["UMBRAL_DIFERIDO_MIN"])
    try:
        with transaction.atomic():
            entrega = EntregaEstudiante.objects.create(
                estudiante=estudiante,
                fecha=fecha,
                supervisor=usuario,
                metodo=metodo,
                motivo=motivo,
                ocurrido_en=ocurrido_en,
                diferido=(timezone.now() - ocurrido_en) > umbral_diferido,
            )
            registrar(
                usuario,
                Accion.ENTREGA_ESTUDIANTE,
                f"{estudiante.nombre_completo} recibió el PAE ({entrega.get_metodo_display()}).",
                objeto=estudiante,
                datos={"fecha": fecha.isoformat(), "metodo": metodo},
                ocurrido_en=ocurrido_en,
                request=request,
            )
    except IntegrityError as exc:
        raise ValidationError(
            {"estudiante": f"{estudiante.nombre_completo} ya recibió el PAE ese día."},
            code="duplicada",
        ) from exc
    return entrega
