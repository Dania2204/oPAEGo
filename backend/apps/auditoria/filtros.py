from django import forms
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import Conductor, Institucion


class FiltroReporteForm(forms.Form):
    """Filtros comunes de reportes e indicadores (RF-32, RF-36)."""

    desde = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    hasta = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    institucion = forms.ModelChoiceField(
        label="Institución",
        queryset=Institucion.objects.all(),
        required=False,
        empty_label="Todas",
    )
    conductor = forms.ModelChoiceField(
        queryset=Conductor.objects.select_related("usuario"), required=False, empty_label="Todos"
    )

    def clean(self):
        datos = super().clean()
        if datos.get("desde") and datos.get("hasta") and datos["desde"] > datos["hasta"]:
            raise forms.ValidationError("La fecha inicial es posterior a la final.")
        return datos


def filtros_desde(parametros):
    form = FiltroReporteForm(parametros)
    if not form.is_valid():
        raise ValidationError(form.errors)
    return form.cleaned_data
