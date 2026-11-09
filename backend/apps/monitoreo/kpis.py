"""RF-32: panel de indicadores.

Las fórmulas son las de la Tabla 3 del documento (línea base / postest):

* Trazabilidad: (entregas con registro completo / total de entregas) × 100
* Control operativo: (entregas a tiempo / total de entregas) × 100
* Control operativo: conteo de novedades (retrasos, daños, faltantes) en el periodo
* Transparencia: (entregas con evidencia verificable / total de entregas) × 100

"Total de entregas" = envíos entregados (con o sin novedad) en el periodo.
"""

from dataclasses import asdict, dataclass

from django.db.models import Prefetch

from apps.envios.estados import ESTADOS_ENTREGADOS, Estado
from apps.envios.models import Envio, ItemEnvio, Novedad


@dataclass
class Indicadores:
    total_envios: int
    total_entregas: int
    entregas_registro_completo: int
    porcentaje_registro_completo: float | None
    entregas_a_tiempo: int
    porcentaje_a_tiempo: float | None
    novedades: int
    novedades_por_tipo: dict
    entregas_con_evidencia: int
    porcentaje_con_evidencia: float | None
    por_estado: dict

    def como_dict(self):
        return asdict(self)


def _porcentaje(parte, total):
    return round(parte * 100 / total, 1) if total else None


def envios_del_periodo(desde=None, hasta=None, institucion=None, conductor=None):
    envios = Envio.objects.select_related(
        "institucion", "conductor__usuario", "vehiculo", "evidencia"
    ).prefetch_related(Prefetch("items", queryset=ItemEnvio.objects.order_by("id")))
    if desde:
        envios = envios.filter(programado_para__date__gte=desde)
    if hasta:
        envios = envios.filter(programado_para__date__lte=hasta)
    if institucion:
        envios = envios.filter(institucion=institucion)
    if conductor:
        envios = envios.filter(conductor=conductor)
    return envios


def calcular(desde=None, hasta=None, institucion=None, conductor=None):
    envios = list(envios_del_periodo(desde, hasta, institucion, conductor))
    entregas = [e for e in envios if e.estado in ESTADOS_ENTREGADOS]
    total = len(entregas)

    completos = sum(1 for e in entregas if e.tiene_registro_completo)
    a_tiempo = sum(1 for e in entregas if e.entregado_a_tiempo)
    con_evidencia = sum(
        1 for e in entregas if getattr(e, "evidencia", None) is not None and e.evidencia.es_integra
    )

    novedades = Novedad.objects.filter(envio__in=[e.pk for e in envios])
    por_tipo = {etiqueta: 0 for _, etiqueta in Novedad.Tipo.choices}
    for tipo in novedades.values_list("tipo", flat=True):
        por_tipo[Novedad.Tipo(tipo).label] += 1

    por_estado = {etiqueta: 0 for _, etiqueta in Estado.choices}
    for e in envios:
        por_estado[Estado(e.estado).label] += 1

    return Indicadores(
        total_envios=len(envios),
        total_entregas=total,
        entregas_registro_completo=completos,
        porcentaje_registro_completo=_porcentaje(completos, total),
        entregas_a_tiempo=a_tiempo,
        porcentaje_a_tiempo=_porcentaje(a_tiempo, total),
        novedades=sum(por_tipo.values()),
        novedades_por_tipo=por_tipo,
        entregas_con_evidencia=con_evidencia,
        porcentaje_con_evidencia=_porcentaje(con_evidencia, total),
        por_estado=por_estado,
    )
