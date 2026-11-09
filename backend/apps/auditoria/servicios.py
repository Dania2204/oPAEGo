"""Servicio único para escribir en el registro de auditoría (RF-33)."""

import contextvars
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import RegistroAuditoria

# Hora "actual" simulada para sembrar datos históricos (comando demo_mes). Cuando
# está activa, `diferido` se calcula contra esta hora y no contra la real, de modo
# que los eventos históricos no se marquen todos como «Sin conexión».
_hora_simulada = contextvars.ContextVar("hora_simulada", default=None)


@contextmanager
def hora_simulada(ts):
    """Dentro de este contexto, registrar() usa `ts` como "ahora" para `diferido`."""
    token = _hora_simulada.set(ts)
    try:
        yield
    finally:
        _hora_simulada.reset(token)


def _ip(request):
    if request is None:
        return None
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def registrar(
    usuario,
    accion,
    descripcion="",
    *,
    objeto=None,
    envio=None,
    datos=None,
    latitud=None,
    longitud=None,
    ocurrido_en=None,
    request=None,
):
    ahora = _hora_simulada.get() or timezone.now()
    ocurrido_en = ocurrido_en or ahora
    umbral = timedelta(minutes=settings.PAEGO["UMBRAL_DIFERIDO_MIN"])
    if usuario is not None and not getattr(usuario, "is_authenticated", False):
        usuario = None
    return RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        entidad=objeto._meta.model_name if objeto is not None else "",
        entidad_id=str(objeto.pk) if objeto is not None else "",
        envio=envio,
        descripcion=descripcion,
        datos=datos or {},
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
        diferido=(ahora - ocurrido_en) > umbral,
        ip=_ip(request),
    )
