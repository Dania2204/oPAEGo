from rest_framework import serializers

from apps.catalogo.simat import etiqueta_grado, etiqueta_jornada
from apps.cuentas.models import Rol

from .models import EntregaEstudiante, Estudiante, MetodoEntrega


class EntregaResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntregaEstudiante
        fields = ["id", "fecha", "metodo", "ocurrido_en"]


class EstudianteSerializer(serializers.ModelSerializer):
    """Para la app del supervisor y de la institución (identidad mínima)."""

    nombre_completo = serializers.CharField(read_only=True)
    grado_etiqueta = serializers.SerializerMethodField()
    curso = serializers.CharField(read_only=True)
    tipo_documento_etiqueta = serializers.CharField(read_only=True)
    jornada_etiqueta = serializers.SerializerMethodField()
    codigo_qr = serializers.SerializerMethodField()
    entrega_del_dia = serializers.SerializerMethodField()

    class Meta:
        model = Estudiante
        fields = [
            "id",
            "tipo_documento",
            "tipo_documento_etiqueta",
            "numero_documento",
            "nombres",
            "apellidos",
            "nombre_completo",
            "grado",
            "grado_etiqueta",
            "grupo",
            "curso",
            "jornada",
            "jornada_etiqueta",
            "codigo_qr",
            "entrega_del_dia",
        ]

    def get_grado_etiqueta(self, obj):
        return etiqueta_grado(obj.grado)

    def get_jornada_etiqueta(self, obj):
        return etiqueta_jornada(obj.jornada) if obj.jornada else ""

    def get_codigo_qr(self, obj):
        # Solo quien registra entregas (supervisor, administrador) recibe el código:
        # la institución consulta pero no puede generar carnés.
        request = self.context.get("request")
        usuario = getattr(request, "user", None)
        if usuario is None or usuario.rol not in (Rol.SUPERVISOR, Rol.ADMINISTRADOR):
            return None
        return obj.codigo_qr

    def get_entrega_del_dia(self, obj):
        entregas = getattr(obj, "entregas_del_dia", None)
        return EntregaResumenSerializer(entregas[0]).data if entregas else None


class EntregaSerializer(serializers.ModelSerializer):
    estudiante_nombre = serializers.CharField(source="estudiante.nombre_completo", read_only=True)
    curso = serializers.CharField(source="estudiante.curso", read_only=True)
    supervisor_nombre = serializers.CharField(source="supervisor.get_full_name", read_only=True)

    class Meta:
        model = EntregaEstudiante
        fields = [
            "id",
            "estudiante",
            "estudiante_nombre",
            "curso",
            "fecha",
            "metodo",
            "motivo",
            "supervisor_nombre",
            "ocurrido_en",
            "diferido",
        ]


# ------------------------------------------------- entradas (operaciones)
class _ConEstudiante(serializers.Serializer):
    estudiante = serializers.IntegerField()
    ocurrido_en = serializers.DateTimeField(required=False, allow_null=True)


class EntregarSerializer(_ConEstudiante):
    metodo = serializers.ChoiceField(choices=MetodoEntrega.choices)
    codigo = serializers.CharField(required=False, allow_blank=True, default="", max_length=64)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    fecha = serializers.DateField(required=False, allow_null=True)
