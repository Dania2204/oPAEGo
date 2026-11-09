from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .operaciones import OPERACIONES, ejecutar

MAX_OPERACIONES = 500


class OperacionSerializer(serializers.Serializer):
    uuid_cliente = serializers.UUIDField()
    tipo = serializers.ChoiceField(choices=sorted(OPERACIONES))
    ocurrido_en = serializers.DateTimeField()
    datos = serializers.DictField()


class LoteSerializer(serializers.Serializer):
    operaciones = OperacionSerializer(many=True)

    def validate_operaciones(self, valor):
        if len(valor) > MAX_OPERACIONES:
            raise serializers.ValidationError(
                f"Máximo {MAX_OPERACIONES} operaciones por lote; envíe el resto en otro lote."
            )
        return valor


class ResultadoSerializer(serializers.Serializer):
    uuid_cliente = serializers.UUIDField()
    tipo = serializers.CharField()
    resultado = serializers.ChoiceField(choices=["ok", "duplicado", "rechazado"])
    respuesta = serializers.DictField()


@extend_schema(
    request=LoteSerializer,
    responses={200: ResultadoSerializer(many=True)},
    description=(
        "RF-38 / RNF-21: recibe las operaciones capturadas sin conexión y las "
        "aplica en orden cronológico (`ocurrido_en`). Cada una se valida con "
        "las mismas reglas que en línea. Es idempotente por `uuid_cliente`: "
        "reenviar un lote no duplica registros."
    ),
)
@api_view(["POST"])
def lote(request):
    serializer = LoteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    operaciones = sorted(serializer.validated_data["operaciones"], key=lambda o: o["ocurrido_en"])
    resultados = []
    for op in operaciones:
        resultado, respuesta = ejecutar(
            request.user,
            op["tipo"],
            op["datos"],
            uuid_cliente=op["uuid_cliente"],
            ocurrido_en=op["ocurrido_en"],
            request=request,
            diferida=True,
        )
        resultados.append(
            {
                "uuid_cliente": str(op["uuid_cliente"]),
                "tipo": op["tipo"],
                "resultado": resultado,
                "respuesta": respuesta,
            }
        )
    return Response({"resultados": resultados})


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
def configuracion(request):
    """Parámetros que usan los clientes (intervalo de ubicación, tolerancias)."""
    return Response(
        {
            "intervalo_ubicacion_seg": settings.PAEGO["INTERVALO_UBICACION_SEG"],
            "intervalo_mapa_seg": settings.PAEGO["INTERVALO_MAPA_SEG"],
            "tolerancia_entrega_min": settings.PAEGO["TOLERANCIA_ENTREGA_MIN"],
            "max_operaciones_lote": MAX_OPERACIONES,
            "operaciones": sorted(OPERACIONES),
        }
    )
