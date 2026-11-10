"""Reglas de la entrega del PAE a estudiantes (rol SUPERVISOR).

API, panel web y sincronización sin conexión pasan por estas funciones: permisos
por institución, consentimiento del acudiente, cifrado de plantillas y auditoría
se aplican siempre igual.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.cuentas.models import Rol
from apps.envios.servicios import normalizar_ocurrido_en

from . import cifrado
from .models import (
    AutorizacionBiometrica,
    EntregaEstudiante,
    Estudiante,
    MetodoEntrega,
    PlantillaFacial,
    Supervisor,
)


class BiometriaNoDisponible(APIException):
    status_code = 503
    default_detail = (
        "El reconocimiento facial no está disponible en el servidor. "
        "Registre la entrega de forma manual."
    )
    default_code = "biometria_no_disponible"


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


def _texto(valor, campo, etiqueta):
    valor = (valor or "").strip()
    if not valor:
        raise ValidationError({campo: f"{etiqueta} es obligatorio."})
    return valor


# --------------------------------------------------------------------------
# Autorización del acudiente
# --------------------------------------------------------------------------
@transaction.atomic
def autorizar(
    usuario,
    estudiante,
    *,
    acudiente_nombre,
    acudiente_documento,
    parentesco,
    ocurrido_en=None,
    request=None,
):
    """Registra la autorización previa, expresa e informada del acudiente."""
    _exigir_acceso(usuario, estudiante)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    datos = {
        "acudiente_nombre": _texto(acudiente_nombre, "acudiente_nombre", "El nombre del acudiente"),
        "acudiente_documento": _texto(
            acudiente_documento, "acudiente_documento", "El documento del acudiente"
        ),
        "parentesco": _texto(parentesco, "parentesco", "El parentesco"),
    }
    actual = (
        AutorizacionBiometrica.objects.select_for_update().filter(estudiante=estudiante).first()
    )
    if actual is not None and actual.vigente:
        raise ValidationError({"estudiante": "El estudiante ya tiene una autorización vigente."})
    if actual is None:
        actual = AutorizacionBiometrica(estudiante=estudiante)
    for campo, valor in datos.items():
        setattr(actual, campo, valor)
    actual.otorgada_en = ocurrido_en
    actual.registrada_por = usuario
    actual.revocada_en = None
    actual.revocada_por = None
    actual.save()
    registrar(
        usuario,
        Accion.AUTORIZACION_BIOMETRICA,
        f"Autorización del acudiente ({datos['parentesco']}) para {estudiante.nombre_completo}.",
        objeto=estudiante,
        ocurrido_en=ocurrido_en,
        request=request,
    )
    return actual


@transaction.atomic
def revocar_autorizacion(usuario, estudiante, *, motivo="", ocurrido_en=None, request=None):
    """El acudiente retira la autorización: se borran las plantillas faciales."""
    _exigir_acceso(usuario, estudiante)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    autorizacion = (
        AutorizacionBiometrica.objects.select_for_update().filter(estudiante=estudiante).first()
    )
    if autorizacion is None or not autorizacion.vigente:
        raise ValidationError({"estudiante": "El estudiante no tiene una autorización vigente."})
    autorizacion.revocada_en = ocurrido_en
    autorizacion.revocada_por = usuario
    autorizacion.save(update_fields=["revocada_en", "revocada_por"])
    registrar(
        usuario,
        Accion.AUTORIZACION_REVOCADA,
        f"Autorización revocada para {estudiante.nombre_completo}. {motivo}".strip(),
        objeto=estudiante,
        ocurrido_en=ocurrido_en,
        request=request,
    )
    borrar_plantillas(estudiante, usuario=usuario, motivo="autorización revocada", request=request)
    return autorizacion


def borrar_plantillas(estudiante, *, usuario=None, motivo="", request=None):
    """Borrado real de las plantillas (no lógico) y constancia en la auditoría."""
    borradas, _ = PlantillaFacial.objects.filter(estudiante=estudiante).delete()
    if borradas:
        registrar(
            usuario,
            Accion.ROSTRO_BORRADO,
            f"Se borraron {borradas} plantillas faciales de {estudiante.nombre_completo} "
            f"({motivo}).",
            objeto=estudiante,
            datos={"plantillas": borradas},
            request=request,
        )
    return borradas


def dar_de_baja(estudiante, *, usuario=None):
    """El estudiante salió de la matrícula: queda inactivo y sin biometría."""
    if estudiante.activo:
        estudiante.activo = False
        estudiante.save(update_fields=["activo", "actualizado_en"])
    return borrar_plantillas(estudiante, usuario=usuario, motivo="retirado de la matrícula")


# --------------------------------------------------------------------------
# Inscripción facial
# --------------------------------------------------------------------------
@transaction.atomic
def inscribir_rostro(usuario, estudiante, *, vectores, modelo, ocurrido_en=None, request=None):
    """Guarda (cifradas) las muestras de la cara del estudiante, como un Face ID.

    Reemplaza una inscripción anterior. Exige autorización vigente del acudiente.
    """
    _exigir_acceso(usuario, estudiante)
    if usuario.rol != Rol.SUPERVISOR:
        raise PermissionDenied("Solo el supervisor inscribe rostros.")
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    if estudiante.autorizacion_vigente is None:
        raise ValidationError(
            {"estudiante": "Falta la autorización del acudiente para registrar el rostro."}
        )
    minimo = settings.PAEGO["MUESTRAS_ROSTRO_MIN"]
    maximo = settings.PAEGO["MUESTRAS_ROSTRO_MAX"]
    if not isinstance(vectores, (list, tuple)) or not minimo <= len(vectores) <= maximo:
        raise ValidationError({"vectores": f"Se necesitan entre {minimo} y {maximo} muestras."})
    modelo = _texto(modelo, "modelo", "El modelo")[:40]
    try:
        limpios = [cifrado.validar_vector(v) for v in vectores]
    except cifrado.VectorInvalido as exc:
        raise ValidationError({"vectores": str(exc)}) from exc
    if len({len(v) for v in limpios}) != 1:
        raise ValidationError({"vectores": "Las muestras tienen dimensiones distintas."})

    PlantillaFacial.objects.filter(estudiante=estudiante).delete()
    try:
        for vector in limpios:
            plantilla = PlantillaFacial(estudiante=estudiante, modelo=modelo)
            plantilla.vector = vector
            plantilla.save()
    except cifrado.BiometriaNoConfigurada as exc:
        raise BiometriaNoDisponible() from exc
    registrar(
        usuario,
        Accion.ROSTRO_INSCRITO,
        f"Rostro inscrito para {estudiante.nombre_completo} ({len(limpios)} muestras).",
        objeto=estudiante,
        datos={"muestras": len(limpios), "modelo": modelo},
        ocurrido_en=ocurrido_en,
        request=request,
    )
    return len(limpios)


def plantillas_de(estudiantes):
    """{estudiante_id: [vector, ...]} descifrados, para reconocer en la app."""
    resultado = {}
    try:
        for plantilla in PlantillaFacial.objects.filter(estudiante__in=estudiantes):
            resultado.setdefault(plantilla.estudiante_id, []).append(plantilla.vector)
    except cifrado.BiometriaNoConfigurada as exc:
        raise BiometriaNoDisponible() from exc
    return resultado


# --------------------------------------------------------------------------
# Entrega diaria
# --------------------------------------------------------------------------
def registrar_entrega(
    usuario,
    estudiante,
    *,
    metodo,
    fecha=None,
    similitud=None,
    motivo="",
    ocurrido_en=None,
    request=None,
):
    """El estudiante recibió el PAE. Una sola vez por día; facial o manual."""
    if usuario.rol not in (Rol.SUPERVISOR, Rol.ADMINISTRADOR):
        raise PermissionDenied("Solo el supervisor registra entregas a estudiantes.")
    _exigir_acceso(usuario, estudiante)
    ocurrido_en = normalizar_ocurrido_en(ocurrido_en)
    fecha = fecha or timezone.localdate(ocurrido_en)
    motivo = (motivo or "").strip()

    if metodo == MetodoEntrega.FACIAL:
        if estudiante.autorizacion_vigente is None:
            raise ValidationError(
                {"metodo": "El estudiante no tiene autorización biométrica vigente."}
            )
        if not estudiante.plantillas.exists():
            raise ValidationError({"metodo": "El estudiante no tiene el rostro inscrito."})
        if similitud is None:
            raise ValidationError({"similitud": "Falta la similitud del reconocimiento."})
        similitud = Decimal(str(similitud)).quantize(Decimal("0.0001"))
        umbral = Decimal(str(settings.PAEGO["UMBRAL_SIMILITUD_FACIAL"]))
        if not umbral <= similitud <= 1:
            raise ValidationError(
                {"similitud": "El reconocimiento no alcanza el umbral; registre la entrega manual."}
            )
    elif metodo == MetodoEntrega.MANUAL:
        if not motivo:
            raise ValidationError({"motivo": "Indique por qué se registra sin cámara."})
        similitud = None
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
                similitud=similitud,
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
