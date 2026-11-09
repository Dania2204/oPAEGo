from decimal import Decimal

from rest_framework import serializers

from apps.catalogo.models import Conductor, Institucion, Vehiculo
from apps.cuentas.models import Rol

from .campos import ImagenBase64Field
from .models import Envio, EvidenciaEntrega, ItemEnvio, Novedad, Ubicacion


# ---------------------------------------------------------------- lectura
class ItemEnvioSerializer(serializers.ModelSerializer):
    unidad_nombre = serializers.CharField(source="get_unidad_display", read_only=True)

    class Meta:
        model = ItemEnvio
        fields = ["id", "producto", "cantidad", "unidad", "unidad_nombre", "cantidad_recibida"]
        read_only_fields = ["id", "cantidad_recibida"]


class InstitucionResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institucion
        fields = ["id", "nombre", "sede", "direccion", "latitud", "longitud", "contacto_telefono"]


class NovedadSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)
    origen_nombre = serializers.CharField(source="get_origen_display", read_only=True)
    reportado_por_nombre = serializers.CharField(
        source="reportado_por.get_full_name", read_only=True
    )
    envio_codigo = serializers.CharField(source="envio.codigo", read_only=True)

    class Meta:
        model = Novedad
        fields = [
            "id",
            "envio",
            "envio_codigo",
            "origen",
            "origen_nombre",
            "tipo",
            "tipo_nombre",
            "descripcion",
            "foto",
            "latitud",
            "longitud",
            "ocurrido_en",
            "recibido_en",
            "reportado_por_nombre",
            "leida_en",
        ]
        read_only_fields = fields


class UbicacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ubicacion
        fields = [
            "id",
            "latitud",
            "longitud",
            "precision_m",
            "velocidad_kmh",
            "rumbo",
            "ocurrido_en",
            "recibido_en",
        ]
        read_only_fields = fields


class EvidenciaSerializer(serializers.ModelSerializer):
    es_integra = serializers.BooleanField(read_only=True)

    class Meta:
        model = EvidenciaEntrega
        fields = [
            "id",
            "recibido_por_nombre",
            "recibido_por_cargo",
            "foto",
            "latitud",
            "longitud",
            "ocurrido_en",
            "recibido_en",
            "huella_sha256",
            "es_integra",
        ]
        read_only_fields = fields


class EnvioSerializer(serializers.ModelSerializer):
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    institucion = InstitucionResumenSerializer(read_only=True)
    conductor_id = serializers.IntegerField(read_only=True)
    conductor_nombre = serializers.CharField(
        source="conductor.usuario.get_full_name", read_only=True
    )
    conductor_telefono = serializers.CharField(source="conductor.telefono", read_only=True)
    vehiculo_placa = serializers.CharField(source="vehiculo.placa", read_only=True, default=None)
    items = ItemEnvioSerializer(many=True, read_only=True)
    esta_retrasado = serializers.BooleanField(read_only=True)
    entregado_a_tiempo = serializers.BooleanField(read_only=True, allow_null=True)
    evidencia = EvidenciaSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Envio
        fields = [
            "id",
            "codigo",
            "programado_para",
            "estado",
            "estado_nombre",
            "institucion",
            "conductor_id",
            "conductor_nombre",
            "conductor_telefono",
            "vehiculo_id",
            "vehiculo_placa",
            "observaciones",
            "codigo_verificacion",
            "items",
            "salida_en",
            "salida_latitud",
            "salida_longitud",
            "llegada_en",
            "llegada_latitud",
            "llegada_longitud",
            "entregado_en",
            "cancelado_en",
            "motivo_cancelacion",
            "esta_retrasado",
            "entregado_a_tiempo",
            "evidencia",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        request = self.context.get("request")
        # La institución no ve el código: debe digitar el que le muestra el conductor.
        if request is not None and getattr(request.user, "rol", None) == Rol.INSTITUCION:
            datos.pop("codigo_verificacion", None)
        return datos


# --------------------------------------------------------------- escritura
class ItemEntradaSerializer(serializers.Serializer):
    producto = serializers.CharField(max_length=150)
    cantidad = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    unidad = serializers.ChoiceField(choices=ItemEnvio.Unidad.choices)


class _ConOcurridoEn(serializers.Serializer):
    ocurrido_en = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="Fecha y hora reales del evento en el dispositivo (RF-38).",
    )


class EnvioCrearSerializer(_ConOcurridoEn):
    """RF-13, RF-14, RF-15."""

    institucion = serializers.PrimaryKeyRelatedField(queryset=Institucion.objects.all())
    conductor = serializers.PrimaryKeyRelatedField(
        queryset=Conductor.objects.select_related("usuario")
    )
    vehiculo = serializers.PrimaryKeyRelatedField(
        queryset=Vehiculo.objects.all(), required=False, allow_null=True
    )
    programado_para = serializers.DateTimeField()
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    items = ItemEntradaSerializer(many=True)


class EnvioEditarSerializer(_ConOcurridoEn):
    """RF-16: modificar antes de la salida."""

    institucion = serializers.PrimaryKeyRelatedField(queryset=Institucion.objects.all())
    vehiculo = serializers.PrimaryKeyRelatedField(
        queryset=Vehiculo.objects.all(), required=False, allow_null=True
    )
    programado_para = serializers.DateTimeField()
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    items = ItemEntradaSerializer(many=True)
    motivo = serializers.CharField()


class ReasignarSerializer(_ConOcurridoEn):
    conductor = serializers.PrimaryKeyRelatedField(
        queryset=Conductor.objects.select_related("usuario")
    )
    vehiculo = serializers.PrimaryKeyRelatedField(
        queryset=Vehiculo.objects.all(), required=False, allow_null=True
    )
    motivo = serializers.CharField()


class MotivoSerializer(_ConOcurridoEn):
    motivo = serializers.CharField()


class PosicionSerializer(_ConOcurridoEn):
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitud = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180
    )


class UbicacionEntradaSerializer(PosicionSerializer):
    precision_m = serializers.DecimalField(
        max_digits=7, decimal_places=2, required=False, allow_null=True
    )
    velocidad_kmh = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True
    )
    rumbo = serializers.IntegerField(min_value=0, max_value=359, required=False, allow_null=True)


class NovedadEntradaSerializer(_ConOcurridoEn):
    tipo = serializers.ChoiceField(choices=Novedad.Tipo.choices)
    descripcion = serializers.CharField()
    foto = ImagenBase64Field(required=False, allow_null=True)
    latitud = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False, allow_null=True
    )
    longitud = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=-180,
        max_value=180,
        required=False,
        allow_null=True,
    )


class ItemRecibidoSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    cantidad_recibida = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class NovedadRecepcionSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=Novedad.Tipo.choices, required=False)
    descripcion = serializers.CharField(required=False, allow_blank=True)
    foto = ImagenBase64Field(required=False, allow_null=True)


class ConfirmacionRecepcionSerializer(_ConOcurridoEn):
    """RF-25, RF-26, RF-27 y RF-28 en una sola operación."""

    items = ItemRecibidoSerializer(many=True)
    recibido_por_nombre = serializers.CharField(max_length=150)
    recibido_por_cargo = serializers.CharField(max_length=100, required=False, allow_blank=True)
    codigo_verificacion = serializers.CharField(max_length=6)
    foto = ImagenBase64Field(required=False, allow_null=True)
    latitud = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False, allow_null=True
    )
    longitud = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=-180,
        max_value=180,
        required=False,
        allow_null=True,
    )
    novedad = NovedadRecepcionSerializer(required=False, allow_null=True)
