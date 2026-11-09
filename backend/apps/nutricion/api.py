from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from apps.cuentas.limite import LimitePorUsuario

from . import gemini

INSTRUCCIONES = """\
Eres un nutricionista experto del Programa de Alimentación Escolar (PAE) en Colombia.
Tu rol es ayudar al usuario {nombre} a llevar una dieta saludable y equilibrada.
Puedes dar recetas, consejos de nutrición, análisis de la dieta del día y sugerencias.
Responde siempre en español, de forma amigable, clara y práctica.
Considera las tradiciones alimentarias colombianas cuando sea relevante.
Si te preguntan algo que no sea de nutrición o alimentación, indícalo con amabilidad.

Contexto nutricional actual del usuario:
{contexto}
"""

ROLES = {"usuario": "user", "asistente": "model"}


class _MensajeSerializer(serializers.Serializer):
    rol = serializers.ChoiceField(choices=list(ROLES))
    texto = serializers.CharField(max_length=2000)


class ConsultaSerializer(serializers.Serializer):
    mensajes = _MensajeSerializer(many=True, min_length=1, max_length=30)
    contexto = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")

    def validate_mensajes(self, mensajes):
        if mensajes[-1]["rol"] != "usuario":
            raise serializers.ValidationError("El último mensaje debe ser del usuario.")
        return mensajes


class _Limite(LimitePorUsuario):
    scope = "nutricion"


@extend_schema(
    request=ConsultaSerializer,
    responses={
        200: inline_serializer("RespuestaNutricion", {"respuesta": serializers.CharField()}),
        502: None,
        503: None,
    },
)
@api_view(["POST"])
@throttle_classes([_Limite])
def asistente(request):
    """Asistente de nutrición de la app móvil: reenvía la conversación a Gemini
    con la clave del servidor. El contexto son los alimentos que el usuario
    registró hoy en la app."""
    consulta = ConsultaSerializer(data=request.data)
    consulta.is_valid(raise_exception=True)
    datos = consulta.validated_data
    instrucciones = INSTRUCCIONES.format(
        nombre=request.user.get_full_name() or request.user.email,
        contexto=datos["contexto"].strip() or "No hay alimentos registrados hoy.",
    )
    mensajes = [(ROLES[m["rol"]], m["texto"]) for m in datos["mensajes"]]
    try:
        texto = gemini.generar(instrucciones, mensajes)
    except gemini.GeminiNoConfigurado:
        return Response(
            {"detail": "El asistente de nutrición no está configurado en el servidor."},
            status=503,
        )
    except gemini.GeminiError:
        return Response(
            {"detail": "El asistente no está disponible en este momento. Intente más tarde."},
            status=502,
        )
    return Response({"respuesta": texto})
