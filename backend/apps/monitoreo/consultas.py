"""Consultas de monitoreo en tiempo real (RF-29 a RF-31)."""

from datetime import timedelta

from django.conf import settings
from django.db.models import F, OuterRef, Subquery, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from apps.envios.estados import Estado
from apps.envios.models import Envio, Novedad, Ubicacion

PUNTOS_RUTA_MAPA = 300


def envios_en_transito():
    """RF-29: envíos en tránsito con su última posición y su recorrido."""
    ultima = Ubicacion.objects.filter(envio=OuterRef("pk")).order_by("-ocurrido_en")
    envios = (
        Envio.objects.filter(estado=Estado.EN_TRANSITO)
        .select_related("institucion", "conductor__usuario", "vehiculo")
        .annotate(
            ultima_latitud=Subquery(ultima.values("latitud")[:1]),
            ultima_longitud=Subquery(ultima.values("longitud")[:1]),
            ultima_en=Subquery(ultima.values("ocurrido_en")[:1]),
        )
    )
    envios = list(envios)
    rutas = _ultimas_rutas([e.pk for e in envios])
    resultado = []
    for envio in envios:
        ruta = rutas.get(envio.pk, [])
        resultado.append(
            {
                "id": envio.pk,
                "codigo": envio.codigo,
                "institucion": str(envio.institucion),
                "destino": [float(envio.institucion.latitud), float(envio.institucion.longitud)],
                "conductor": envio.conductor.usuario.get_full_name(),
                "telefono": envio.conductor.telefono,
                "vehiculo": envio.vehiculo.placa if envio.vehiculo else None,
                "programado_para": envio.programado_para.isoformat(),
                "salida_en": envio.salida_en.isoformat() if envio.salida_en else None,
                "llegada_en": envio.llegada_en.isoformat() if envio.llegada_en else None,
                "retrasado": envio.esta_retrasado,
                "posicion": (
                    [float(envio.ultima_latitud), float(envio.ultima_longitud)]
                    if envio.ultima_latitud is not None
                    else None
                ),
                "posicion_en": envio.ultima_en.isoformat() if envio.ultima_en else None,
                "ruta": [[float(lat), float(lng)] for lat, lng in ruta],
            }
        )
    return resultado


def _ultimas_rutas(envio_ids):
    """Últimos PUNTOS_RUTA_MAPA puntos de cada envío, en orden cronológico,
    con una sola consulta (antes era una por envío)."""
    if not envio_ids:
        return {}
    puntos = (
        Ubicacion.objects.filter(envio_id__in=envio_ids)
        .annotate(
            orden=Window(
                RowNumber(), partition_by=[F("envio_id")], order_by=F("ocurrido_en").desc()
            )
        )
        .filter(orden__lte=PUNTOS_RUTA_MAPA)
        .order_by("envio_id", "ocurrido_en", "id")
        .values_list("envio_id", "latitud", "longitud")
    )
    rutas = {}
    for envio_id, lat, lng in puntos:
        rutas.setdefault(envio_id, []).append((lat, lng))
    return rutas


def alertas_retraso():
    """RF-30: envíos que superaron la hora programada (más la tolerancia) sin
    ser entregados."""
    limite = timezone.now() - timedelta(minutes=settings.PAEGO["TOLERANCIA_ENTREGA_MIN"])
    return (
        Envio.objects.filter(
            estado__in=[Estado.ASIGNADO, Estado.EN_TRANSITO], programado_para__lt=limite
        )
        .select_related("institucion", "conductor__usuario")
        .order_by("programado_para")
    )


def novedades_sin_leer():
    """RF-31: novedades reportadas pendientes de atención por el administrador."""
    return (
        Novedad.objects.filter(leida_en__isnull=True)
        .select_related("envio", "reportado_por")
        .order_by("-ocurrido_en")
    )


def _orden_grado(codigo):
    try:
        return (0, int(codigo))
    except (TypeError, ValueError):
        return (1, codigo)


def cobertura(anio=None):
    """Matrícula agregada por institución, grado y jornada (Anexo 6A de SIMAT).

    Trabaja solo sobre conteos (modelo MatriculaSede); no hay datos de
    estudiantes. Alimenta el reporte de cobertura y, como total por sede, la
    sugerencia de raciones (RF-14)."""
    from apps.catalogo.models import MatriculaSede
    from apps.catalogo.simat import etiqueta_grado, etiqueta_jornada

    anios = sorted(MatriculaSede.objects.values_list("anio", flat=True).distinct(), reverse=True)
    if anio is None and anios:
        anio = anios[0]

    qs = MatriculaSede.objects.select_related("institucion")
    if anio:
        qs = qs.filter(anio=anio)

    instituciones = {}
    grados = {}
    jornadas = {}
    total = 0
    for m in qs:
        total += m.total
        inst = instituciones.setdefault(
            m.institucion_id,
            {"institucion": m.institucion, "total": 0, "grados": {}, "jornadas": {}},
        )
        inst["total"] += m.total
        inst["grados"][m.grado] = inst["grados"].get(m.grado, 0) + m.total
        inst["jornadas"][m.jornada] = inst["jornadas"].get(m.jornada, 0) + m.total
        grados[m.grado] = grados.get(m.grado, 0) + m.total
        jornadas[m.jornada] = jornadas.get(m.jornada, 0) + m.total

    def _lista_grados(dic):
        return [(etiqueta_grado(g), dic[g]) for g in sorted(dic, key=_orden_grado)]

    def _lista_jornadas(dic):
        return [(etiqueta_jornada(j), dic[j]) for j in sorted(dic, key=_orden_grado)]

    filas = sorted(instituciones.values(), key=lambda d: str(d["institucion"]))
    for fila in filas:
        fila["grados"] = _lista_grados(fila["grados"])
        fila["jornadas"] = _lista_jornadas(fila["jornadas"])

    return {
        "anio": anio,
        "anios": anios,
        "total": total,
        "instituciones": filas,
        "por_grado": _lista_grados(grados),
        "por_jornada": _lista_jornadas(jornadas),
    }
