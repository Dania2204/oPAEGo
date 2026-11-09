from rest_framework import serializers

from .models import RegistroAuditoria


class RegistroAuditoriaSerializer(serializers.ModelSerializer):
    accion_nombre = serializers.CharField(source="get_accion_display", read_only=True)
    usuario_nombre = serializers.SerializerMethodField()
    usuario_rol = serializers.CharField(source="usuario.rol", read_only=True, default=None)
    envio_codigo = serializers.CharField(source="envio.codigo", read_only=True, default=None)

    class Meta:
        model = RegistroAuditoria
        fields = [
            "id",
            "accion",
            "accion_nombre",
            "descripcion",
            "usuario",
            "usuario_nombre",
            "usuario_rol",
            "entidad",
            "entidad_id",
            "envio",
            "envio_codigo",
            "latitud",
            "longitud",
            "ocurrido_en",
            "registrado_en",
            "diferido",
            "datos",
        ]
        read_only_fields = fields

    def get_usuario_nombre(self, obj) -> str:
        return obj.usuario.get_full_name() if obj.usuario else "Sistema"
