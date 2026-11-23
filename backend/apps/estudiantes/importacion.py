"""Actualización de la matrícula de una institución desde el Anexo 6A de SIMAT.

Una sola fuente de reglas para el panel web (subir el Excel) y el comando
`importar_estudiantes`:

- Del Anexo solo se leen las columnas de identidad mínima (PER_ID, documento,
  nombres, apellidos, grado, grupo, jornada y sede). `leer_anexo` nunca entrega
  las demás (dirección, teléfono, SISBÉN, víctima, discapacidad, etnia, fecha de
  nacimiento, ...). Ley 1581: minimización de datos de menores.
- El Anexo 6A es municipal: se filtra por el CODIGO_DANE de la institución.
- Idempotente por PER_ID: actualiza a quien ya existe (p. ej. cambia de curso al
  pasar de año), crea a los nuevos con su código QR y da de baja (inactivo; su QR
  deja de servir) a quien ya no aparece (p. ej. los que terminaron 11°).
- Los estudiantes agregados a mano (`PREFIJO_MANUAL`) se reconocen por su
  documento y reciben su PER_ID real; si el archivo no los trae se conservan.
"""

from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.catalogo.simat import AnexoInvalido, etiqueta_grado, leer_anexo

from . import servicios
from .models import PREFIJO_MANUAL, EstadoImportacion, Estudiante

COLUMNAS = [
    "PER_ID",
    "CODIGO_DANE",
    "CONS_SEDE",
    "TIPO_DOCUMENTO",
    "NRO_DOCUMENTO",
    "APELLIDO1",
    "APELLIDO2",
    "NOMBRE1",
    "NOMBRE2",
    "GRADO",
    "GRUPO",
    "TIPO_JORNADA",
]

# Población del PAE: de transición a 11°. Preescolar menor y ciclos de adultos no.
GRADOS_PAE = frozenset(str(g) for g in range(12))

CAMPOS = (
    "tipo_documento",
    "numero_documento",
    "nombres",
    "apellidos",
    "grado",
    "grupo",
    "jornada",
    "sede_simat",
)


def texto(valor):
    """Celda de Excel como texto: 1085123456.0 → «1085123456»."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _nombre(*partes):
    return " ".join(texto(p).title() for p in partes if texto(p))


def curso(grado, grupo):
    return f"{etiqueta_grado(grado)} {grupo}".strip()


def leer(archivo, codigos_dane, grados=GRADOS_PAE):
    """Filas del Anexo de esos CODIGO_DANE como {per_id: datos} (identidad mínima).

    `grados=None` lee todos los grados. Lanza `AnexoInvalido` si el archivo no
    sirve o no trae estudiantes de la institución.
    """
    danes = {texto(d) for d in codigos_dane if texto(d)}
    leidos = {}
    otros_danes = set()
    for fila in leer_anexo(archivo, COLUMNAS):
        dane = texto(fila["CODIGO_DANE"])
        if dane not in danes:
            otros_danes.add(dane)
            continue
        if grados is not None and texto(fila["GRADO"]) not in grados:
            continue
        per_id = texto(fila["PER_ID"])
        if not per_id:
            continue
        leidos[per_id] = {
            "tipo_documento": texto(fila["TIPO_DOCUMENTO"])[:10],
            "numero_documento": texto(fila["NRO_DOCUMENTO"])[:20],
            "nombres": _nombre(fila["NOMBRE1"], fila["NOMBRE2"])[:100],
            "apellidos": _nombre(fila["APELLIDO1"], fila["APELLIDO2"])[:100],
            "grado": texto(fila["GRADO"])[:4],
            "grupo": texto(fila["GRUPO"])[:10],
            "jornada": texto(fila["TIPO_JORNADA"])[:2],
            "sede_simat": texto(fila["CONS_SEDE"])[:20],
        }
    if not leidos:
        detalle = (
            f" El archivo trae {len(otros_danes)} códigos DANE distintos."
            if otros_danes
            else " El archivo no trae filas."
        )
        raise AnexoInvalido(
            f"No hay estudiantes con el código DANE {', '.join(sorted(danes)) or '(vacío)'}."
            + detalle
        )
    return leidos


def _orden_curso(par):
    grado, grupo = par
    try:
        return (int(grado), grupo)
    except ValueError:
        return (99, grupo)


def _por_curso(contador):
    return [
        {"curso": curso(*par), "cantidad": n}
        for par, n in sorted(contador.items(), key=lambda x: _orden_curso(x[0]))
    ]


def _comparar(institucion, leidos, *, escribir):
    """Compara el archivo con la base y, si `escribir`, aplica los cambios."""
    por_per_id = {e.simat_per_id: e for e in Estudiante.objects.filter(simat_per_id__in=leidos)}
    manuales = {
        e.numero_documento: e
        for e in Estudiante.objects.filter(
            institucion=institucion, simat_per_id__startswith=PREFIJO_MANUAL
        )
    }
    nuevos, bajas = Counter(), Counter()
    movimientos = Counter()
    cuenta = Counter()
    tocados = set()

    for per_id, datos in leidos.items():
        estudiante = por_per_id.get(per_id) or manuales.pop(datos["numero_documento"], None)
        if estudiante is None:
            nuevos[(datos["grado"], datos["grupo"])] += 1
            cuenta["nuevos"] += 1
            if escribir:
                nuevo = Estudiante.objects.create(
                    simat_per_id=per_id, institucion=institucion, **datos
                )
                tocados.add(nuevo.pk)
            continue
        tocados.add(estudiante.pk)
        cambios = {c: datos[c] for c in CAMPOS if getattr(estudiante, c) != datos[c]}
        if estudiante.simat_per_id != per_id:
            cambios["simat_per_id"] = per_id
        if estudiante.institucion_id != institucion.pk:
            cambios["institucion"] = institucion
            cuenta["trasladados"] += 1
        if not estudiante.activo:
            cambios["activo"] = True
            cuenta["reactivados"] += 1
        elif "grado" in cambios or "grupo" in cambios:
            movimientos[
                (curso(estudiante.grado, estudiante.grupo), curso(datos["grado"], datos["grupo"]))
            ] += 1
            cuenta["cambian_curso"] += 1
        elif cambios:
            cuenta["corregidos"] += 1
        else:
            cuenta["sin_cambios"] += 1
        if cambios and escribir:
            for campo, valor in cambios.items():
                setattr(estudiante, campo, valor)
            estudiante.save()

    retirados = (
        Estudiante.objects.filter(institucion=institucion, activo=True)
        .exclude(pk__in=tocados)
        .exclude(simat_per_id__startswith=PREFIJO_MANUAL)
    )
    for estudiante in retirados:
        bajas[(estudiante.grado, estudiante.grupo)] += 1
        cuenta["bajas"] += 1
        if escribir:
            servicios.dar_de_baja(estudiante)

    manuales_sin_archivo = sum(1 for e in manuales.values() if e.activo)
    activos_antes = Estudiante.objects.filter(institucion=institucion, activo=True).count()
    return {
        "leidos": len(leidos),
        "nuevos": cuenta["nuevos"],
        "cambian_curso": cuenta["cambian_curso"],
        "reactivados": cuenta["reactivados"],
        "trasladados": cuenta["trasladados"],
        "corregidos": cuenta["corregidos"],
        "sin_cambios": cuenta["sin_cambios"],
        "bajas": cuenta["bajas"],
        "manuales_conservados": manuales_sin_archivo,
        "activos_antes": activos_antes if not escribir else None,
        "nuevos_por_curso": _por_curso(nuevos),
        "bajas_por_curso": _por_curso(bajas),
        "movimientos": [
            {"de": de, "a": a, "cantidad": n} for (de, a), n in movimientos.most_common(40)
        ],
    }


def planear(institucion, leidos):
    """Qué cambiaría si se aplica el archivo (no escribe nada)."""
    return _comparar(institucion, leidos, escribir=False)


@transaction.atomic
def aplicar(institucion, leidos, *, usuario=None, request=None, nombre_archivo=""):
    resumen = _comparar(institucion, leidos, escribir=True)
    registrar(
        usuario,
        Accion.MATRICULA_ACTUALIZADA,
        f"Matrícula de {institucion} actualizada desde SIMAT"
        f"{f' ({nombre_archivo})' if nombre_archivo else ''}: {resumen['nuevos']} nuevos, "
        f"{resumen['cambian_curso']} cambian de curso, {resumen['bajas']} dados de baja.",
        objeto=institucion,
        datos={
            k: resumen[k]
            for k in ("leidos", "nuevos", "cambian_curso", "reactivados", "bajas", "corregidos")
        },
        request=request,
    )
    return resumen


@transaction.atomic
def confirmar(importacion, usuario, *, request=None):
    """Aplica una importación pendiente (paso 2 del panel web)."""
    importacion = type(importacion).objects.select_for_update().get(pk=importacion.pk)
    if importacion.estado != EstadoImportacion.PENDIENTE:
        raise ValueError("Esta importación ya se aplicó o se descartó.")
    resumen = aplicar(
        importacion.institucion,
        importacion.filas,
        usuario=usuario,
        request=request,
        nombre_archivo=importacion.nombre_archivo,
    )
    institucion = importacion.institucion
    if not institucion.codigo_dane:
        institucion.codigo_dane = importacion.codigo_dane
        institucion.save(update_fields=["codigo_dane", "actualizado_en"])
    importacion.estado = EstadoImportacion.APLICADA
    importacion.aplicado_en = timezone.now()
    importacion.resumen = resumen
    importacion.filas = {}  # la copia del archivo no se guarda (Ley 1581)
    importacion.save()
    return resumen


def descartar(importacion):
    if importacion.estado == EstadoImportacion.PENDIENTE:
        importacion.estado = EstadoImportacion.DESCARTADA
        importacion.filas = {}
        importacion.save(update_fields=["estado", "filas"])
