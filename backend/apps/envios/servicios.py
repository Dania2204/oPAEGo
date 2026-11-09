"""Reglas de negocio de los envíos.

Todas las operaciones (API, panel web y sincronización sin conexión) pasan
por estas funciones, de modo que permisos, transiciones de estado (RF-18) y
auditoría (RF-33) se aplican siempre igual.
"""

import hashlib
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.cuentas.models import Rol

from .estados import Estado, puede_transicionar
from .models import EvidenciaEntrega, ItemEnvio, Novedad, Ubicacion


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def normalizar_ocurrido_en(valor):
    """RF-38: hora real del evento. Sin valor, se toma la hora del servidor."""
    ahora = timezone.now()
    if valor is None:
        return ahora
    if timezone.is_naive(valor):
        valor = timezone.make_aware(valor)
    tolerancia = timedelta(minutes=settings.PAEGO["TOLERANCIA_RELOJ_MIN"])
    if valor > ahora + tolerancia:
        raise ValidationError({"ocurrido_en": "La fecha del evento está en el futuro."})
    return valor


def _exigir_rol(usuario, rol):
    if usuario.rol != rol:
        raise PermissionDenied("Su rol no tiene permiso para realizar esta acción.")


def _cambiar_estado(envio, destino, usuario):
    if not puede_transicionar(envio.estado, destino, usuario.rol):
        raise ValidationError(
            {
                "estado": (
                    f"No se puede pasar de «{envio.get_estado_display()}» a "
                    f"«{Estado(destino).label}» con el rol {usuario.get_rol_display()}."
                )
            }
        )
    envio.estado = destino


def conductor_de(usuario):
    _exigir_rol(usuario, Rol.CONDUCTOR)
    conductor = getattr(usuario, "conductor", None)
    if conductor is None or not conductor.activo:
        raise PermissionDenied("El usuario no está registrado como conductor activo.")
    return conductor


def institucion_de(usuario):
    _exigir_rol(usuario, Rol.INSTITUCION)
    responsable = getattr(usuario, "responsable_recepcion", None)
    if responsable is None or not responsable.activo:
        raise PermissionDenied("El usuario no es responsable de recepción activo.")
    return responsable.institucion


def _exigir_conductor_del_envio(usuario, envio):
    conductor = conductor_de(usuario)
    if envio.conductor_id != conductor.pk:
        raise PermissionDenied("Este envío no está asignado a usted.")
    return conductor


def _exigir_institucion_del_envio(usuario, envio):
    institucion = institucion_de(usuario)
    if envio.institucion_id != institucion.pk:
        raise PermissionDenied("Este envío no está dirigido a su institución.")
    return institucion


def _validar_asignacion(institucion, conductor, vehiculo):
    errores = {}
    if not institucion.activo:
        errores["institucion"] = "La institución está desactivada."
    if not conductor.activo or not conductor.usuario.is_active:
        errores["conductor"] = "El conductor está desactivado."
    if vehiculo is not None:
        if not vehiculo.activo:
            errores["vehiculo"] = "El vehículo está desactivado."
        elif vehiculo.conductor_id and vehiculo.conductor_id != conductor.pk:
            errores["vehiculo"] = "El vehículo está asociado a otro conductor."
    if errores:
        raise ValidationError(errores)


def _validar_items(items):
    if not items:
        raise ValidationError({"items": "Registre al menos un alimento."})
    for item in items:
        if Decimal(item["cantidad"]) <= 0:
            raise ValidationError({"items": "Las cantidades deben ser mayores que cero."})


def _items_resumen(envio):
    return [
        {"producto": i.producto, "cantidad": str(i.cantidad), "unidad": i.unidad}
        for i in envio.items.all()
    ]


def _sha256_archivo(archivo):
    if not archivo:
        return ""
    digest = hashlib.sha256()
    archivo.seek(0)
    for bloque in archivo.chunks():
        digest.update(bloque)
    archivo.seek(0)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Administrador: RF-13 a RF-17
# --------------------------------------------------------------------------
@transaction.atomic
def crear_envio(
    usuario,
    *,
    institucion,
    conductor,
    programado_para,
    items,
    vehiculo=None,
    observaciones="",
    ocurrido_en=None,
    request=None,
):
    from .models import Envio

    _exigir_rol(usuario, Rol.ADMINISTRADOR)
    _validar_asignacion(institucion, conductor, vehiculo)
    _validar_items(items)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    envio = Envio.objects.create(
        programado_para=programado_para,
        institucion=institucion,
        conductor=conductor,
        vehiculo=vehiculo,
        observaciones=observaciones,
        creado_por=usuario,
        estado=Estado.ASIGNADO,
    )
    ItemEnvio.objects.bulk_create(ItemEnvio(envio=envio, **item) for item in items)
    registrar(
        usuario,
        Accion.ENVIO_CREADO,
        f"Envío {envio.codigo} para {institucion} asignado a {conductor.usuario.get_full_name()}",
        objeto=envio,
        envio=envio,
        ocurrido_en=ocurrido_en,
        request=request,
        datos={"items": _items_resumen(envio), "programado_para": programado_para.isoformat()},
    )
    return envio


def _exigir_antes_de_salida(envio):
    if envio.estado != Estado.ASIGNADO or envio.salida_en:
        raise ValidationError(
            {"estado": "Solo se puede modificar, reasignar o cancelar un envío antes de su salida."}
        )


def _exigir_motivo(motivo):
    if not (motivo or "").strip():
        raise ValidationError({"motivo": "Debe registrar el motivo."})


@transaction.atomic
def editar_envio(
    usuario,
    envio,
    *,
    motivo,
    institucion,
    programado_para,
    items,
    vehiculo=None,
    observaciones="",
    ocurrido_en=None,
    request=None,
):
    """RF-16: modificar antes de la salida, registrando el motivo."""
    _exigir_rol(usuario, Rol.ADMINISTRADOR)
    _exigir_antes_de_salida(envio)
    _exigir_motivo(motivo)
    _validar_asignacion(institucion, envio.conductor, vehiculo)
    _validar_items(items)
    antes = {
        "institucion": str(envio.institucion),
        "programado_para": envio.programado_para.isoformat(),
        "vehiculo": str(envio.vehiculo) if envio.vehiculo else None,
        "items": _items_resumen(envio),
    }
    envio.institucion = institucion
    envio.programado_para = programado_para
    envio.vehiculo = vehiculo
    envio.observaciones = observaciones
    envio.save()
    envio.items.all().delete()
    ItemEnvio.objects.bulk_create(ItemEnvio(envio=envio, **item) for item in items)
    despues = {
        "institucion": str(institucion),
        "programado_para": programado_para.isoformat(),
        "vehiculo": str(vehiculo) if vehiculo else None,
        "items": _items_resumen(envio),
    }
    registrar(
        usuario,
        Accion.ENVIO_EDITADO,
        f"Envío {envio.codigo} modificado. Motivo: {motivo}",
        objeto=envio,
        envio=envio,
        ocurrido_en=normalizar_ocurrido_en(ocurrido_en),
        request=request,
        datos={"motivo": motivo, "antes": antes, "despues": despues},
    )
    return envio


@transaction.atomic
def reasignar_envio(
    usuario, envio, *, conductor, motivo, vehiculo=None, ocurrido_en=None, request=None
):
    """RF-16: reasignar conductor (y vehículo) antes de la salida."""
    _exigir_rol(usuario, Rol.ADMINISTRADOR)
    _exigir_antes_de_salida(envio)
    _exigir_motivo(motivo)
    _validar_asignacion(envio.institucion, conductor, vehiculo)
    anterior = envio.conductor
    envio.conductor = conductor
    envio.vehiculo = vehiculo
    envio.save()
    registrar(
        usuario,
        Accion.ENVIO_REASIGNADO,
        f"Envío {envio.codigo} reasignado de {anterior.usuario.get_full_name()} a "
        f"{conductor.usuario.get_full_name()}. Motivo: {motivo}",
        objeto=envio,
        envio=envio,
        ocurrido_en=normalizar_ocurrido_en(ocurrido_en),
        request=request,
        datos={
            "motivo": motivo,
            "conductor_anterior": anterior.pk,
            "conductor_nuevo": conductor.pk,
        },
    )
    return envio


@transaction.atomic
def cancelar_envio(usuario, envio, *, motivo, ocurrido_en=None, request=None):
    """RF-16: cancelar antes de la salida, registrando el motivo."""
    _exigir_rol(usuario, Rol.ADMINISTRADOR)
    _exigir_motivo(motivo)
    _exigir_antes_de_salida(envio)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    _cambiar_estado(envio, Estado.CANCELADO, usuario)
    envio.cancelado_en = ocurrido_en
    envio.motivo_cancelacion = motivo
    envio.save()
    registrar(
        usuario,
        Accion.ENVIO_CANCELADO,
        f"Envío {envio.codigo} cancelado. Motivo: {motivo}",
        objeto=envio,
        envio=envio,
        ocurrido_en=ocurrido_en,
        request=request,
        datos={"motivo": motivo},
    )
    return envio


@transaction.atomic
def cerrar_con_novedad(usuario, envio, *, motivo, ocurrido_en=None, request=None):
    """El administrador cierra un envío en tránsito que no pudo entregarse
    (por ejemplo, un accidente). Queda registrado como novedad."""
    _exigir_rol(usuario, Rol.ADMINISTRADOR)
    _exigir_motivo(motivo)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    _cambiar_estado(envio, Estado.CON_NOVEDAD, usuario)
    envio.save()
    Novedad.objects.create(
        envio=envio,
        reportado_por=usuario,
        origen=Novedad.Origen.ADMINISTRACION,
        tipo=Novedad.Tipo.INCIDENTE,
        descripcion=motivo,
        ocurrido_en=ocurrido_en,
        leida_en=timezone.now(),
        leida_por=usuario,
    )
    registrar(
        usuario,
        Accion.CIERRE_CON_NOVEDAD,
        f"Envío {envio.codigo} cerrado con novedad: {motivo}",
        objeto=envio,
        envio=envio,
        ocurrido_en=ocurrido_en,
        request=request,
        datos={"motivo": motivo},
    )
    return envio


def marcar_novedad_leida(usuario, novedad):
    """RF-31: el administrador marca la notificación como atendida."""
    _exigir_rol(usuario, Rol.ADMINISTRADOR)
    if novedad.leida_en is None:
        novedad.leida_en = timezone.now()
        novedad.leida_por = usuario
        novedad.save(update_fields=["leida_en", "leida_por"])
    return novedad


# --------------------------------------------------------------------------
# Conductor: RF-20 a RF-23
# --------------------------------------------------------------------------
@transaction.atomic
def registrar_salida(usuario, envio, *, latitud, longitud, ocurrido_en=None, request=None):
    conductor = _exigir_conductor_del_envio(usuario, envio)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    _cambiar_estado(envio, Estado.EN_TRANSITO, usuario)
    envio.salida_en = ocurrido_en
    envio.salida_latitud = latitud
    envio.salida_longitud = longitud
    envio.save()
    Ubicacion.objects.create(
        envio=envio,
        conductor=conductor,
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
    )
    registrar(
        usuario,
        Accion.SALIDA,
        f"Salida del envío {envio.codigo}",
        objeto=envio,
        envio=envio,
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
        request=request,
    )
    return envio


def registrar_ubicacion(
    usuario,
    envio,
    *,
    latitud,
    longitud,
    precision_m=None,
    velocidad_kmh=None,
    rumbo=None,
    ocurrido_en=None,
):
    """RF-21. Se aceptan posiciones tardías (sincronizadas sin conexión)
    siempre que sean posteriores a la salida: el recorrido no se pierde."""
    conductor = _exigir_conductor_del_envio(usuario, envio)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    if envio.estado == Estado.CANCELADO or not envio.salida_en:
        raise ValidationError({"estado": "El envío no está en tránsito."})
    if ocurrido_en < envio.salida_en - timedelta(minutes=1):
        raise ValidationError({"ocurrido_en": "La ubicación es anterior a la salida."})
    return Ubicacion.objects.create(
        envio=envio,
        conductor=conductor,
        latitud=latitud,
        longitud=longitud,
        precision_m=precision_m,
        velocidad_kmh=velocidad_kmh,
        rumbo=rumbo,
        ocurrido_en=ocurrido_en,
    )


@transaction.atomic
def registrar_llegada(usuario, envio, *, latitud, longitud, ocurrido_en=None, request=None):
    conductor = _exigir_conductor_del_envio(usuario, envio)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    if envio.estado == Estado.CANCELADO or not envio.salida_en:
        raise ValidationError({"estado": "Debe registrar la salida antes de la llegada."})
    if envio.llegada_en:
        raise ValidationError({"estado": "La llegada ya fue registrada."})
    envio.llegada_en = ocurrido_en
    envio.llegada_latitud = latitud
    envio.llegada_longitud = longitud
    envio.save()
    Ubicacion.objects.create(
        envio=envio,
        conductor=conductor,
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
    )
    registrar(
        usuario,
        Accion.LLEGADA,
        f"Llegada del envío {envio.codigo} a {envio.institucion}",
        objeto=envio,
        envio=envio,
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
        request=request,
    )
    return envio


@transaction.atomic
def reportar_novedad(
    usuario,
    envio,
    *,
    tipo,
    descripcion,
    foto=None,
    latitud=None,
    longitud=None,
    ocurrido_en=None,
    request=None,
):
    """RF-23 (conductor, en el trayecto) y RF-28 (institución, en la recepción)."""
    if usuario.rol == Rol.CONDUCTOR:
        _exigir_conductor_del_envio(usuario, envio)
        origen = Novedad.Origen.TRAYECTO
    elif usuario.rol == Rol.INSTITUCION:
        _exigir_institucion_del_envio(usuario, envio)
        origen = Novedad.Origen.RECEPCION
    else:
        raise PermissionDenied("Solo el conductor o la institución reportan novedades.")
    if envio.estado == Estado.CANCELADO:
        raise ValidationError({"estado": "El envío está cancelado."})
    if not (descripcion or "").strip():
        raise ValidationError({"descripcion": "Describa la novedad."})
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    novedad = Novedad.objects.create(
        envio=envio,
        reportado_por=usuario,
        origen=origen,
        tipo=tipo,
        descripcion=descripcion,
        foto=foto,
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
    )
    # Hallazgo posterior a una recepción conforme: la entrega queda con novedad.
    if origen == Novedad.Origen.RECEPCION and envio.estado == Estado.ENTREGADO:
        _cambiar_estado(envio, Estado.CON_NOVEDAD, usuario)
        envio.save(update_fields=["estado", "actualizado_en"])
    registrar(
        usuario,
        Accion.NOVEDAD,
        f"Novedad «{novedad.get_tipo_display()}» en {envio.codigo}: {descripcion}",
        objeto=novedad,
        envio=envio,
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
        request=request,
        datos={"tipo": tipo, "origen": origen},
    )
    return novedad


# --------------------------------------------------------------------------
# Institución: RF-25 a RF-28
# --------------------------------------------------------------------------
@transaction.atomic
def confirmar_recepcion(
    usuario,
    envio,
    *,
    items_recibidos,
    recibido_por_nombre,
    codigo_verificacion,
    recibido_por_cargo="",
    foto=None,
    latitud=None,
    longitud=None,
    novedad=None,
    ocurrido_en=None,
    request=None,
):
    """RF-25 verificar cantidades, RF-26 confirmar, RF-27 evidencia, RF-28 novedad."""
    _exigir_institucion_del_envio(usuario, envio)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    if envio.estado != Estado.EN_TRANSITO:
        raise ValidationError({"estado": "Solo se puede recibir un envío en tránsito."})
    if str(codigo_verificacion).strip() != envio.codigo_verificacion:
        raise ValidationError({"codigo_verificacion": "El código de verificación no coincide."})
    if not (recibido_por_nombre or "").strip():
        raise ValidationError({"recibido_por_nombre": "Indique quién recibe."})

    items = {i.pk: i for i in envio.items.all()}
    recibidos = {int(r["item"]): Decimal(str(r["cantidad_recibida"])) for r in items_recibidos}
    if set(recibidos) != set(items):
        raise ValidationError({"items": "Registre la cantidad recibida de todos los alimentos."})
    diferencias = []
    for pk, item in items.items():
        if recibidos[pk] < 0:
            raise ValidationError({"items": "Las cantidades recibidas no pueden ser negativas."})
        item.cantidad_recibida = recibidos[pk]
        item.save(update_fields=["cantidad_recibida"])
        if recibidos[pk] != item.cantidad:
            diferencias.append(
                f"{item.producto}: programado {item.cantidad}, recibido {recibidos[pk]} "
                f"{item.get_unidad_display().lower()}"
            )

    novedades = []
    if diferencias:
        novedades.append(
            Novedad.objects.create(
                envio=envio,
                reportado_por=usuario,
                origen=Novedad.Origen.RECEPCION,
                tipo=Novedad.Tipo.FALTANTE,
                descripcion="; ".join(diferencias),
                latitud=latitud,
                longitud=longitud,
                ocurrido_en=ocurrido_en,
            )
        )
    if novedad and (novedad.get("descripcion") or "").strip():
        novedades.append(
            Novedad.objects.create(
                envio=envio,
                reportado_por=usuario,
                origen=Novedad.Origen.RECEPCION,
                tipo=novedad.get("tipo") or Novedad.Tipo.ENTREGA_INCOMPLETA,
                descripcion=novedad["descripcion"],
                foto=novedad.get("foto"),
                latitud=latitud,
                longitud=longitud,
                ocurrido_en=ocurrido_en,
            )
        )

    destino = Estado.CON_NOVEDAD if novedades else Estado.ENTREGADO
    _cambiar_estado(envio, destino, usuario)
    envio.entregado_en = ocurrido_en
    envio.save()

    evidencia = EvidenciaEntrega(
        envio=envio,
        registrado_por=usuario,
        recibido_por_nombre=recibido_por_nombre.strip(),
        recibido_por_cargo=recibido_por_cargo,
        codigo_verificacion=str(codigo_verificacion).strip(),
        foto=foto,
        foto_sha256=_sha256_archivo(foto),
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
    )
    evidencia.huella_sha256 = evidencia.calcular_huella()
    evidencia.save()

    for n in novedades:
        registrar(
            usuario,
            Accion.NOVEDAD,
            f"Novedad «{n.get_tipo_display()}» en {envio.codigo}: {n.descripcion}",
            objeto=n,
            envio=envio,
            latitud=latitud,
            longitud=longitud,
            ocurrido_en=ocurrido_en,
            request=request,
            datos={"tipo": n.tipo, "origen": n.origen},
        )
    registrar(
        usuario,
        Accion.RECEPCION_CON_NOVEDAD if novedades else Accion.RECEPCION_CONFIRMADA,
        f"Recepción del envío {envio.codigo} por {evidencia.recibido_por_nombre}",
        objeto=evidencia,
        envio=envio,
        latitud=latitud,
        longitud=longitud,
        ocurrido_en=ocurrido_en,
        request=request,
        datos={"huella_sha256": evidencia.huella_sha256, "diferencias": diferencias},
    )
    return envio
