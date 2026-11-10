from rest_framework import serializers

from apps.catalogo.simat import etiqueta_grado

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
    autorizacion_vigente = serializers.SerializerMethodField()
    rostro_inscrito = serializers.SerializerMethodField()
    entrega_del_dia = serializers.SerializerMethodField()

    class Meta:
        model = Estudiante
        fields = [
            "id",
            "tipo_documento",
            "numero_documento",
            "nombres",
            "apellidos",
            "nombre_completo",
            "grado",
            "grado_etiqueta",
            "grupo",
            "curso",
            "jornada",
            "autorizacion_vigente",
            "rostro_inscrito",
            "entrega_del_dia",
        ]

    def get_grado_etiqueta(self, obj):
        return etiqueta_grado(obj.grado)

    def get_autorizacion_vigente(self, obj):
        return obj.autorizacion_vigente is not None

    def get_rostro_inscrito(self, obj):
        # Anotado en la consulta (`num_plantillas`) para no hacer N+1.
        return getattr(obj, "num_plantillas", 0) > 0

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
            "similitud",
            "supervisor_nombre",
            "ocurrido_en",
            "diferido",
        ]


# ------------------------------------------------- entradas (operaciones)
class _ConEstudiante(serializers.Serializer):
    estudiante = serializers.IntegerField()
    ocurrido_en = serializers.DateTimeField(required=False, allow_null=True)


class AutorizarSerializer(_ConEstudiante):
    acudiente_nombre = serializers.CharField(max_length=150)
    acudiente_documento = serializers.CharField(max_length=20)
    parentesco = serializers.CharField(max_length=50)


class RevocarSerializer(_ConEstudiante):
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class InscribirSerializer(_ConEstudiante):
    vectores = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), allow_empty=False),
        allow_empty=False,
        max_length=10,
    )
    modelo = serializers.CharField(max_length=40)


class EntregarSerializer(_ConEstudiante):
    metodo = serializers.ChoiceField(choices=MetodoEntrega.choices)
    similitud = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=1)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    fecha = serializers.DateField(required=False, allow_null=True)
