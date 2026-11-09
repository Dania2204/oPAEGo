"""Panel web: operación del día, indicadores y novedades (RF-29 a RF-32)."""

import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from rest_framework.exceptions import PermissionDenied

from apps.auditoria.filtros import FiltroReporteForm
from apps.catalogo.models import Conductor, Institucion
from apps.comun import disparar, responder
from apps.cuentas.models import Rol
from apps.cuentas.permisos import AdministradorRequeridoMixin
from apps.envios.estados import Estado
from apps.envios.models import Envio, Novedad
from apps.envios.servicios import conductor_de, marcar_novedad_leida

from . import consultas, kpis

MINUTOS_PROXIMO = 60


def _envios_de_hoy():
    """Lo que el despachador mira hoy: lo programado para hoy, lo que va en
    ruta y lo atrasado de días anteriores."""
    hoy = timezone.localdate()
    limite = timezone.now() - timedelta(minutes=settings.PAEGO["TOLERANCIA_ENTREGA_MIN"])
    return (
        Envio.objects.filter(
            Q(programado_para__date=hoy)
            | Q(estado=Estado.EN_TRANSITO)
            | Q(estado=Estado.ASIGNADO, programado_para__lt=limite)
        )
        .select_related("institucion", "conductor__usuario", "vehiculo")
        .order_by("programado_para")
    )


class HoyView(AdministradorRequeridoMixin, View):
    """Página de inicio: excepciones primero, luego mapa y lista del día."""

    def get(self, request):
        ahora = timezone.now()
        hoy = timezone.localdate()
        envios = list(_envios_de_hoy())
        en_transito = {e["id"]: e for e in consultas.envios_en_transito()}

        grupos = [
            ("En ruta", [e for e in envios if e.estado == Estado.EN_TRANSITO]),
            ("Por salir", [e for e in envios if e.estado == Estado.ASIGNADO]),
            (
                "Entregados",
                [e for e in envios if e.estado in (Estado.ENTREGADO, Estado.CON_NOVEDAD)],
            ),
            ("Cancelados", [e for e in envios if e.estado == Estado.CANCELADO]),
        ]
        retrasados = list(consultas.alertas_retraso())
        novedades = list(consultas.novedades_sin_leer()[:8])
        proximos = [
            e
            for e in envios
            if e.estado == Estado.ASIGNADO
            and ahora <= e.programado_para <= ahora + timedelta(minutes=MINUTOS_PROXIMO)
        ]

        mapa = []
        for e in envios:
            if e.estado == Estado.CANCELADO:
                continue
            vivo = en_transito.get(e.pk, {})
            mapa.append(
                {
                    "id": e.pk,
                    "codigo": e.codigo,
                    "estado": e.estado,
                    "institucion": str(e.institucion),
                    "conductor": e.conductor.usuario.get_full_name(),
                    "destino": [float(e.institucion.latitud), float(e.institucion.longitud)],
                    "posicion": vivo.get("posicion"),
                    "posicion_en": vivo.get("posicion_en"),
                    "ruta": vivo.get("ruta", []),
                    "retrasado": e.esta_retrasado,
                }
            )

        contexto = {
            "grupos": [(titulo, lista) for titulo, lista in grupos if lista],
            "total_hoy": sum(1 for e in envios if timezone.localdate(e.programado_para) == hoy),
            "en_ruta": len(grupos[0][1]),
            "entregados": len(grupos[2][1]),
            "retrasados": retrasados,
            "novedades": novedades,
            "novedades_total": consultas.novedades_sin_leer().count(),
            "proximos": proximos,
            "hay_atencion": bool(retrasados or novedades or proximos),
            "mapa_json": json.dumps(mapa),
            "actualizado": ahora,
            "hoy_ymd": hoy.strftime("%Y%m%d"),
        }
        return responder(
            request, "monitoreo/hoy.html", contexto, {"estado-hoy": "monitoreo/_hoy_estado.html"}
        )


def _semanas(desde, hasta):
    """Lunes y domingo de cada semana del periodo."""
    inicio = desde - timedelta(days=desde.weekday())
    while inicio <= hasta:
        yield max(inicio, desde), min(inicio + timedelta(days=6), hasta)
        inicio += timedelta(days=7)


class IndicadoresView(AdministradorRequeridoMixin, View):
    """RF-32: los cuatro indicadores de la Tabla 3, su tendencia semanal y el
    desglose por institución y conductor."""

    def get(self, request):
        hoy = timezone.localdate()
        filtros = FiltroReporteForm(
            request.GET or {"desde": hoy - timedelta(weeks=8), "hasta": hoy}
        )
        datos = filtros.cleaned_data if filtros.is_valid() else {}
        desde = datos.get("desde") or hoy - timedelta(weeks=8)
        hasta = datos.get("hasta") or hoy
        institucion = datos.get("institucion")
        conductor = datos.get("conductor")

        total = kpis.calcular(desde, hasta, institucion, conductor)
        serie = []
        for lunes, domingo in _semanas(desde, hasta):
            k = kpis.calcular(lunes, domingo, institucion, conductor)
            serie.append(
                {
                    "semana": lunes.strftime("%d/%m"),
                    "registro_completo": k.porcentaje_registro_completo,
                    "a_tiempo": k.porcentaje_a_tiempo,
                    "con_evidencia": k.porcentaje_con_evidencia,
                    "novedades": k.novedades,
                    "entregas": k.total_entregas,
                }
            )

        periodo = Envio.objects.filter(
            programado_para__date__gte=desde, programado_para__date__lte=hasta
        )
        por_institucion = [
            (i, kpis.calcular(desde, hasta, i, conductor))
            for i in Institucion.objects.filter(pk__in=periodo.values("institucion")).order_by(
                "nombre"
            )
            if not institucion or i == institucion
        ]
        por_conductor = [
            (c, kpis.calcular(desde, hasta, institucion, c))
            for c in Conductor.objects.filter(pk__in=periodo.values("conductor")).select_related(
                "usuario"
            )
            if not conductor or c == conductor
        ]
        contexto = {
            "filtros": filtros,
            "total": total,
            "serie": serie,
            "serie_json": json.dumps(serie),
            "por_institucion": por_institucion,
            "por_conductor": por_conductor,
            "desde": desde,
            "hasta": hasta,
        }
        return responder(
            request,
            "monitoreo/indicadores.html",
            contexto,
            {"resultado-indicadores": "monitoreo/_indicadores.html"},
        )


class CoberturaView(AdministradorRequeridoMixin, View):
    """Reporte de cobertura: matrícula (beneficiarios) por institución, grado y
    jornada, a partir del Anexo 6A de SIMAT importado. Solo conteos agregados."""

    def get(self, request):
        anio = request.GET.get("anio")
        datos = consultas.cobertura(int(anio) if anio and anio.isdigit() else None)
        return responder(request, "monitoreo/cobertura.html", datos)


class ConductorEnVivoView(View):
    """Modo de prueba: el conductor comparte su ubicación desde el navegador
    del celular mientras tiene la sesión abierta (luego lo hará la app móvil)."""

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.rol != Rol.CONDUCTOR:
            return redirect("cuentas:inicio")
        try:
            conductor = conductor_de(request.user)
        except PermissionDenied:
            return render(request, "cuentas/sin_acceso_web.html", status=403)
        vehiculo = conductor.vehiculos.filter(activo=True).first()
        return render(
            request,
            "monitoreo/conductor_en_vivo.html",
            {"conductor": conductor, "vehiculo": vehiculo},
        )


class MapaView(AdministradorRequeridoMixin, View):
    """El mapa en tiempo real ahora vive en «Hoy» (RF-29)."""

    def get(self, request):
        return redirect("monitoreo:panel")


def _novedades_filtradas(request):
    novedades = Novedad.objects.select_related(
        "envio", "envio__institucion", "reportado_por", "leida_por"
    )
    estado = request.GET.get("estado", "pendientes")
    if estado == "pendientes":
        novedades = novedades.filter(leida_en__isnull=True)
    tipo = request.GET.get("tipo")
    if tipo:
        novedades = novedades.filter(tipo=tipo)
    return novedades.order_by("-ocurrido_en"), estado, tipo


class NovedadesView(AdministradorRequeridoMixin, View):
    """RF-31: bandeja de novedades reportadas por conductores e instituciones."""

    def get(self, request, pk=None):
        novedades, estado, tipo = _novedades_filtradas(request)
        pagina = Paginator(novedades, 30).get_page(request.GET.get("pagina"))
        seleccionada = None
        if pk:
            seleccionada = get_object_or_404(Novedad.objects.select_related("envio"), pk=pk)
        elif pagina.object_list:
            seleccionada = pagina.object_list[0]
        parametros = request.GET.copy()
        parametros.pop("pagina", None)
        contexto = {
            "pagina": pagina,
            "estado": estado,
            "tipo": tipo,
            "tipos": Novedad.Tipo.choices,
            "seleccionada": seleccionada,
            "parametros": parametros.urlencode(),
        }
        return responder(
            request,
            "monitoreo/novedades.html",
            contexto,
            {
                "novedad-detalle": "monitoreo/_novedad.html",
                "bandeja": "monitoreo/_bandeja.html",
            },
        )

    def post(self, request, pk=None):
        """Marca la novedad como atendida (compatible con formularios sin JS)."""
        novedad = get_object_or_404(Novedad, pk=pk or request.POST.get("novedad"))
        marcar_novedad_leida(request.user, novedad)
        messages.success(request, "Novedad marcada como atendida.")
        if request.headers.get("HX-Request") == "true":
            respuesta = responder(
                request,
                "monitoreo/_novedad.html",
                {"seleccionada": novedad, "oob_avisos": True},
            )
            return disparar(respuesta, "novedades-actualizadas")
        return redirect(request.POST.get("volver") or "monitoreo:novedades")
