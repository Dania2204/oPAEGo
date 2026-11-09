from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.auditoria.api import PARAMETROS_REPORTE
from apps.auditoria.filtros import filtros_desde
from apps.cuentas.permisos import EsAdministrador, EsConductor
from apps.envios.models import Novedad
from apps.envios.serializers import EnvioSerializer, NovedadSerializer, UbicacionEntradaSerializer
from apps.envios.servicios import marcar_novedad_leida

from . import consultas, en_vivo, kpis


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([EsAdministrador])
def en_transito(request):
    """RF-29: posición y ruta de los envíos en tránsito."""
    return Response(consultas.envios_en_transito())


@extend_schema(request=UbicacionEntradaSerializer, responses={204: None})
@api_view(["POST"])
@permission_classes([EsConductor])
def mi_posicion(request):
    """Mapa en vivo (modo de prueba): el conductor con sesión abierta transmite
    su posición actual."""
    serializer = UbicacionEntradaSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    datos = dict(serializer.validated_data)
    datos.pop("ocurrido_en", None)
    en_vivo.actualizar_posicion(request.user, **datos)
    return Response(status=204)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([EsAdministrador])
def conductores_en_vivo(request):
    """Mapa en vivo (modo de prueba): conductores conectados y su posición."""
    return Response(en_vivo.conductores_en_vivo())


@extend_schema(responses=EnvioSerializer(many=True))
@api_view(["GET"])
@permission_classes([EsAdministrador])
def alertas(request):
    """RF-30: envíos que superaron la hora programada sin ser entregados."""
    datos = EnvioSerializer(consultas.alertas_retraso(), many=True, context={"request": request})
    return Response(datos.data)


@extend_schema(responses=NovedadSerializer(many=True))
@api_view(["GET"])
@permission_classes([EsAdministrador])
def novedades_pendientes(request):
    """RF-31: novedades pendientes de atención."""
    return Response(NovedadSerializer(consultas.novedades_sin_leer(), many=True).data)


@extend_schema(request=None, responses=NovedadSerializer)
@api_view(["POST"])
@permission_classes([EsAdministrador])
def marcar_leida(request, pk):
    novedad = marcar_novedad_leida(request.user, get_object_or_404(Novedad, pk=pk))
    return Response(NovedadSerializer(novedad).data)


@extend_schema(parameters=PARAMETROS_REPORTE, responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@permission_classes([EsAdministrador])
def indicadores(request):
    """RF-32: indicadores de la Tabla 3 (entregas a tiempo, con evidencia,
    con registro completo y novedades)."""
    filtros = filtros_desde(request.query_params)
    return Response(kpis.calcular(**filtros).como_dict())
