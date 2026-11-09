import django_filters

from .estados import Estado
from .models import Envio


class EnvioFilter(django_filters.FilterSet):
    """RF-17: filtrar por fecha, estado, institución y conductor."""

    fecha_desde = django_filters.DateFilter(field_name="programado_para", lookup_expr="date__gte")
    fecha_hasta = django_filters.DateFilter(field_name="programado_para", lookup_expr="date__lte")
    estado = django_filters.MultipleChoiceFilter(choices=Estado.choices)
    codigo = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = Envio
        fields = ["fecha_desde", "fecha_hasta", "estado", "institucion", "conductor", "codigo"]
