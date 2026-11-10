"""Consultas de lectura de la entrega a estudiantes (API, panel e indicadores)."""

from django.db.models import Count, Prefetch, Q

from apps.catalogo.simat import etiqueta_grado

from .models import EntregaEstudiante


def _orden_grado(grado):
    try:
        return int(grado)
    except (TypeError, ValueError):
        return 99


def con_estado_del_dia(qs, fecha):
    """Anota plantillas y precarga la entrega de `fecha` (sin consultas N+1)."""
    return (
        qs.select_related("autorizacion")
        .annotate(num_plantillas=Count("plantillas", distinct=True))
        # Con agregados Django ignora Meta.ordering: orden explícito para paginar.
        .order_by("grado", "grupo", "apellidos", "nombres", "id")
        .prefetch_related(
            Prefetch(
                "entregas",
                queryset=EntregaEstudiante.objects.filter(fecha=fecha),
                to_attr="entregas_del_dia",
            )
        )
    )


def resumen_cursos(estudiantes, fecha):
    """Por curso: activos, con rostro inscrito y cuántos recibieron en `fecha`."""
    filas = (
        estudiantes.filter(activo=True)
        .values("institucion_id", "institucion__nombre", "grado", "grupo")
        .annotate(
            activos=Count("id", distinct=True),
            con_rostro=Count("id", filter=Q(plantillas__isnull=False), distinct=True),
            recibieron=Count("id", filter=Q(entregas__fecha=fecha), distinct=True),
        )
    )
    cursos = []
    for f in filas:
        cursos.append(
            {
                "institucion": f["institucion_id"],
                "institucion_nombre": f["institucion__nombre"],
                "grado": f["grado"],
                "grupo": f["grupo"],
                "curso": f"{etiqueta_grado(f['grado'])} {f['grupo']}".strip(),
                "activos": f["activos"],
                "con_rostro": f["con_rostro"],
                "recibieron": f["recibieron"],
            }
        )
    cursos.sort(key=lambda c: (c["institucion_nombre"], _orden_grado(c["grado"]), c["grupo"]))
    return cursos


def cobertura(estudiantes, fecha):
    """Totales del día: activos, recibieron y porcentaje (None sin estudiantes)."""
    activos = estudiantes.filter(activo=True).count()
    recibieron = (
        EntregaEstudiante.objects.filter(estudiante__in=estudiantes, fecha=fecha)
        .values("estudiante")
        .distinct()
        .count()
    )
    porcentaje = round(100 * recibieron / activos, 1) if activos else None
    return {"activos": activos, "recibieron": recibieron, "porcentaje": porcentaje}


def estudiantes_del_curso(estudiantes, grado, grupo=None):
    qs = estudiantes.filter(activo=True, grado=grado)
    return qs if grupo in (None, "") else qs.filter(grupo=grupo)
