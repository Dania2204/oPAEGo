"""Panel web: registro de auditoría (RF-33) y reportes (RF-36, RF-37)."""

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.views import View

from apps.comun import responder
from apps.cuentas.permisos import AdministradorRequeridoMixin

from . import reportes
from .api import respuesta_archivo
from .filtros import FiltroReporteForm
from .models import Accion, RegistroAuditoria


class AuditoriaView(AdministradorRequeridoMixin, View):
    def get(self, request):
        registros = RegistroAuditoria.objects.select_related("usuario", "envio")
        accion = request.GET.get("accion")
        usuario = request.GET.get("usuario")
        desde = request.GET.get("desde")
        hasta = request.GET.get("hasta")
        if accion:
            registros = registros.filter(accion=accion)
        if usuario:
            registros = registros.filter(usuario_id=usuario)
        if desde:
            registros = registros.filter(ocurrido_en__date__gte=desde)
        if hasta:
            registros = registros.filter(ocurrido_en__date__lte=hasta)
        if request.GET.get("diferido"):
            registros = registros.filter(diferido=True)
        parametros = request.GET.copy()
        parametros.pop("pagina", None)
        return responder(
            request,
            "auditoria/lista.html",
            {
                "pagina": Paginator(registros, 50).get_page(request.GET.get("pagina")),
                "acciones": Accion.choices,
                "usuarios": get_user_model().objects.order_by("first_name"),
                "parametros": parametros.urlencode(),
            },
            {"resultados": "auditoria/_tabla.html"},
        )


class ReportesView(AdministradorRequeridoMixin, View):
    def get(self, request):
        filtros = FiltroReporteForm(request.GET or None)
        reporte = None
        if filtros.is_valid():
            reporte = reportes.construir(**filtros.cleaned_data)
            formato = request.GET.get("formato")
            if formato in ("xlsx", "pdf"):
                return respuesta_archivo(request, reporte, formato)
        parametros = request.GET.copy()
        parametros.pop("formato", None)
        return responder(
            request,
            "auditoria/reportes.html",
            {"filtros": filtros, "reporte": reporte, "parametros": parametros.urlencode()},
            {"resultados": "auditoria/_reporte.html"},
        )
