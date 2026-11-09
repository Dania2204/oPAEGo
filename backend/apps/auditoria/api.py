from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cuentas.permisos import EsAdministrador

from . import reportes
from .filtros import filtros_desde
from .models import Accion, RegistroAuditoria
from .serializers import RegistroAuditoriaSerializer
from .servicios import registrar

PARAMETROS_REPORTE = [
    OpenApiParameter("desde", OpenApiTypes.DATE),
    OpenApiParameter("hasta", OpenApiTypes.DATE),
    OpenApiParameter("institucion", OpenApiTypes.INT),
    OpenApiParameter("conductor", OpenApiTypes.INT),
]


class RegistroAuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """RF-33: registro de auditoría. Solo lectura (RNF-12)."""

    permission_classes = [EsAdministrador]
    serializer_class = RegistroAuditoriaSerializer
    queryset = RegistroAuditoria.objects.select_related("usuario", "envio")
    filterset_fields = ["accion", "usuario", "envio", "diferido"]
    search_fields = ["descripcion"]


class ReporteView(APIView):
    """RF-36 / RF-37: reporte por periodo, institución y conductor.

    `formato`: json (por defecto), xlsx o pdf.
    """

    permission_classes = [EsAdministrador]

    @extend_schema(
        parameters=PARAMETROS_REPORTE
        + [OpenApiParameter("formato", OpenApiTypes.STR, enum=["json", "xlsx", "pdf"])],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        filtros = filtros_desde(request.query_params)
        reporte = reportes.construir(**filtros)
        formato = request.query_params.get("formato", "json")
        if formato == "json":
            return Response(reporte)
        return respuesta_archivo(request, reporte, formato)


def respuesta_archivo(request, reporte, formato):
    marca = reporte["generado_en"].replace(" ", "_").replace(":", "")
    if formato == "xlsx":
        contenido = reportes.a_excel(reporte)
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif formato == "pdf":
        contenido = reportes.a_pdf(reporte)
        tipo = "application/pdf"
    else:
        return HttpResponse("Formato no soportado.", status=400)
    registrar(
        request.user,
        Accion.EXPORTAR_REPORTE,
        f"Reporte exportado en {formato.upper()}",
        request=request,
        datos={"filtros": reporte["filtros"]},
    )
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = f'attachment; filename="reporte_paego_{marca}.{formato}"'
    return respuesta
