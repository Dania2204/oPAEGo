"""Catálogo de operaciones que un cliente puede ejecutar (en línea o sin conexión).

RF-38 / RNF-21: cada operación lleva un `uuid_cliente` generado en el
dispositivo. Si llega dos veces se devuelve el resultado guardado, por lo
que reintentar una sincronización nunca duplica registros.
"""

import uuid

from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.catalogo import servicios as catalogo
from apps.catalogo.models import Conductor, Institucion, ResponsableRecepcion, Vehiculo
from apps.catalogo.serializers import (
    ConductorSerializer,
    InstitucionSerializer,
    ResponsableRecepcionSerializer,
    VehiculoSerializer,
)
from apps.envios import servicios as envios
from apps.envios.models import Envio
from apps.envios.serializers import (
    ConfirmacionRecepcionSerializer,
    EnvioCrearSerializer,
    EnvioEditarSerializer,
    MotivoSerializer,
    NovedadEntradaSerializer,
    PosicionSerializer,
    ReasignarSerializer,
    UbicacionEntradaSerializer,
)

from .models import OperacionCliente


def _validar(serializer_class, datos):
    serializer = serializer_class(data=datos)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def _envio(datos):
    envio_id = datos.get("envio")
    if envio_id in (None, ""):
        raise ValidationError({"envio": "Indique el envío."})
    return get_object_or_404(Envio.objects.select_for_update(), pk=envio_id)


def _resultado(objeto):
    return {"entidad": objeto._meta.model_name, "id": objeto.pk}


# --------------------------------------------------------------- envíos
def _envio_crear(usuario, datos, request):
    v = _validar(EnvioCrearSerializer, datos)
    envio = envios.crear_envio(usuario, request=request, **v)
    return {**_resultado(envio), "codigo": envio.codigo}


def _envio_editar(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(EnvioEditarSerializer, datos)
    return _resultado(envios.editar_envio(usuario, envio, request=request, **v))


def _envio_reasignar(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(ReasignarSerializer, datos)
    return _resultado(envios.reasignar_envio(usuario, envio, request=request, **v))


def _envio_cancelar(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(MotivoSerializer, datos)
    return _resultado(envios.cancelar_envio(usuario, envio, request=request, **v))


def _envio_cerrar_con_novedad(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(MotivoSerializer, datos)
    return _resultado(envios.cerrar_con_novedad(usuario, envio, request=request, **v))


def _envio_salida(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(PosicionSerializer, datos)
    return _resultado(envios.registrar_salida(usuario, envio, request=request, **v))


def _envio_ubicacion(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(UbicacionEntradaSerializer, datos)
    return _resultado(envios.registrar_ubicacion(usuario, envio, **v))


def _envio_llegada(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(PosicionSerializer, datos)
    return _resultado(envios.registrar_llegada(usuario, envio, request=request, **v))


def _envio_novedad(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(NovedadEntradaSerializer, datos)
    return _resultado(envios.reportar_novedad(usuario, envio, request=request, **v))


def _envio_confirmar(usuario, datos, request):
    envio = _envio(datos)
    v = _validar(ConfirmacionRecepcionSerializer, datos)
    v["items_recibidos"] = v.pop("items")
    envio = envios.confirmar_recepcion(usuario, envio, request=request, **v)
    return {**_resultado(envio), "estado": envio.estado}


# ------------------------------------------------------------- catálogo
def _catalogo(modelo, serializer_class, crear):
    def manejador(usuario, datos, request):
        datos = dict(datos)
        ocurrido_en = datos.pop("ocurrido_en", None)
        if isinstance(ocurrido_en, str):
            ocurrido_en = parse_datetime(ocurrido_en)
        instancia = None
        if not crear:
            instancia = get_object_or_404(modelo, pk=datos.pop("id", None))
        objeto = catalogo.guardar(
            usuario,
            serializer_class,
            datos,
            instancia=instancia,
            ocurrido_en=ocurrido_en,
            request=request,
        )
        return _resultado(objeto)

    return manejador


OPERACIONES = {
    "envio.crear": _envio_crear,
    "envio.editar": _envio_editar,
    "envio.reasignar": _envio_reasignar,
    "envio.cancelar": _envio_cancelar,
    "envio.cerrar_con_novedad": _envio_cerrar_con_novedad,
    "envio.salida": _envio_salida,
    "envio.ubicacion": _envio_ubicacion,
    "envio.llegada": _envio_llegada,
    "envio.novedad": _envio_novedad,
    "envio.confirmar": _envio_confirmar,
    "institucion.crear": _catalogo(Institucion, InstitucionSerializer, True),
    "institucion.editar": _catalogo(Institucion, InstitucionSerializer, False),
    "conductor.crear": _catalogo(Conductor, ConductorSerializer, True),
    "conductor.editar": _catalogo(Conductor, ConductorSerializer, False),
    "vehiculo.crear": _catalogo(Vehiculo, VehiculoSerializer, True),
    "vehiculo.editar": _catalogo(Vehiculo, VehiculoSerializer, False),
    "responsable.crear": _catalogo(ResponsableRecepcion, ResponsableRecepcionSerializer, True),
    "responsable.editar": _catalogo(ResponsableRecepcion, ResponsableRecepcionSerializer, False),
}


def _detalle_error(exc):
    if isinstance(exc, APIException):
        return exc.detail
    return str(exc)


def ejecutar(
    usuario,
    tipo,
    datos,
    *,
    uuid_cliente=None,
    ocurrido_en=None,
    request=None,
    diferida=False,
    propagar=False,
):
    """Ejecuta una operación y devuelve (resultado, respuesta).

    resultado ∈ {"ok", "duplicado", "rechazado"}. Los rechazos de negocio
    (validación, permisos, no encontrado) se guardan para que un reintento
    obtenga la misma respuesta; los errores inesperados no, así el cliente
    puede reintentar. Con `propagar=True` (API directa) el rechazo se lanza
    como excepción para que DRF responda con el código HTTP adecuado.
    """
    manejador = OPERACIONES.get(tipo)
    if manejador is None:
        if propagar:
            raise ValidationError({"tipo": f"Operación desconocida: {tipo}"})
        return "rechazado", {"detalle": f"Operación desconocida: {tipo}"}

    if uuid_cliente:
        previa = OperacionCliente.objects.filter(uuid_cliente=uuid_cliente).first()
        if previa is not None:
            if previa.usuario_id != usuario.pk:
                if propagar:
                    raise ValidationError({"uuid_cliente": "El identificador ya fue usado."})
                return "rechazado", {"detalle": "El identificador de operación ya fue usado."}
            return "duplicado", previa.respuesta

    datos = dict(datos or {})
    if ocurrido_en is not None and "ocurrido_en" not in datos:
        datos["ocurrido_en"] = ocurrido_en

    try:
        with transaction.atomic():
            _resolver_referencias(usuario, datos)
            respuesta = manejador(usuario, datos, request)
            if uuid_cliente:
                OperacionCliente.objects.create(
                    uuid_cliente=uuid_cliente,
                    usuario=usuario,
                    tipo=tipo,
                    ocurrido_en=_fecha_segura(datos.get("ocurrido_en")),
                    resultado=OperacionCliente.Resultado.OK,
                    respuesta=_serializable(respuesta),
                )
        return "ok", respuesta
    except IntegrityError:
        # Otra petición simultánea registró el mismo uuid_cliente.
        previa = OperacionCliente.objects.filter(uuid_cliente=uuid_cliente).first()
        if uuid_cliente and previa is not None and previa.usuario_id == usuario.pk:
            return "duplicado", previa.respuesta
        raise
    except (Http404, ValidationError, PermissionDenied, NotFound) as exc:
        error = exc
        if isinstance(exc, Http404):
            error = NotFound("El registro indicado no existe.")
        respuesta = _serializable({"detalle": _detalle_error(error)})

    if uuid_cliente:
        OperacionCliente.objects.create(
            uuid_cliente=uuid_cliente,
            usuario=usuario,
            tipo=tipo,
            ocurrido_en=_fecha_segura(datos.get("ocurrido_en")),
            resultado=OperacionCliente.Resultado.RECHAZADA,
            respuesta=respuesta,
        )
    if diferida:
        envio_id = datos.get("envio")
        envio = Envio.objects.filter(pk=envio_id).first() if str(envio_id or "").isdigit() else None
        registrar(
            usuario,
            Accion.SINCRONIZACION_RECHAZADA,
            f"Operación sin conexión «{tipo}» rechazada",
            envio=envio,
            ocurrido_en=_fecha_segura(datos.get("ocurrido_en")),
            request=request,
            datos={"uuid_cliente": str(uuid_cliente), "motivo": respuesta},
        )
    if propagar:
        raise error
    return "rechazado", respuesta


CAMPOS_REFERENCIA = ("envio", "id", "institucion", "conductor", "vehiculo")


def _resolver_referencias(usuario, datos):
    """Un registro creado sin conexión todavía no tiene id en el servidor; el
    cliente lo referencia con el `uuid_cliente` de la operación que lo creó."""
    for campo in CAMPOS_REFERENCIA:
        valor = datos.get(campo)
        if not isinstance(valor, str) or len(valor) != 36:
            continue
        try:
            referencia = uuid.UUID(valor)
        except ValueError:
            continue
        previa = OperacionCliente.objects.filter(
            uuid_cliente=referencia, usuario=usuario, resultado=OperacionCliente.Resultado.OK
        ).first()
        if previa is None or "id" not in previa.respuesta:
            raise ValidationError(
                {campo: "El registro referenciado no se ha sincronizado o fue rechazado."}
            )
        datos[campo] = previa.respuesta["id"]


def _fecha(valor):
    if isinstance(valor, str):
        return parse_datetime(valor)
    return valor


def _fecha_segura(valor):
    from django.utils import timezone

    fecha = _fecha(valor)
    if fecha is None:
        return timezone.now()
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    return min(fecha, timezone.now())


def _serializable(valor):
    """Convierte ErrorDetail y estructuras anidadas a tipos JSON."""
    if isinstance(valor, dict):
        return {str(k): _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_serializable(v) for v in valor]
    return str(valor) if not isinstance(valor, (int, float, bool, type(None))) else valor
