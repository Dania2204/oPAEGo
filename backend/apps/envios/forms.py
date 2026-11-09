from django import forms

from apps.catalogo.models import Conductor, Institucion, Vehiculo

from .estados import Estado
from .models import ItemEnvio


def _conductores():
    return Conductor.objects.filter(activo=True, usuario__is_active=True).select_related("usuario")


class EnvioForm(forms.Form):
    """RF-13 a RF-15. Los ítems (RF-14) llegan como listas item_producto,
    item_cantidad e item_unidad y se arman en `items`."""

    institucion = forms.ModelChoiceField(
        label="Institución de destino",
        queryset=Institucion.objects.filter(activo=True),
        empty_label="Elegir institución…",
    )
    programado_para = forms.DateTimeField(
        label="Fecha y hora programadas",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    conductor = forms.ModelChoiceField(queryset=_conductores(), empty_label="Elegir conductor…")
    vehiculo = forms.ModelChoiceField(
        label="Vehículo",
        queryset=Vehiculo.objects.filter(activo=True),
        required=False,
        empty_label="Sin vehículo",
    )
    observaciones = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    motivo = forms.CharField(
        label="Motivo de la modificación",
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )

    def __init__(self, *args, edicion=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conductor"].queryset = _conductores()
        if edicion:
            # RF-16: el conductor se cambia con "reasignar"; al modificar se exige motivo.
            del self.fields["conductor"]
            self.fields["motivo"].required = True
        else:
            del self.fields["motivo"]

    def items(self):
        productos = self.data.getlist("item_producto")
        cantidades = self.data.getlist("item_cantidad")
        unidades = self.data.getlist("item_unidad")
        return [
            {"producto": p.strip(), "cantidad": c, "unidad": u}
            for p, c, u in zip(productos, cantidades, unidades, strict=False)
            if p.strip() or c
        ]


UNIDADES = ItemEnvio.Unidad.choices


class ReasignarForm(forms.Form):
    conductor = forms.ModelChoiceField(queryset=_conductores(), empty_label="Elegir conductor…")
    vehiculo = forms.ModelChoiceField(
        queryset=Vehiculo.objects.filter(activo=True), required=False, empty_label="Sin vehículo"
    )
    motivo = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conductor"].queryset = _conductores()


class MotivoForm(forms.Form):
    motivo = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))


class FiltroEnviosForm(forms.Form):
    """RF-17."""

    fecha_desde = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    fecha_hasta = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    estado = forms.ChoiceField(choices=[("", "Todos")] + Estado.choices, required=False)
    institucion = forms.ModelChoiceField(
        queryset=Institucion.objects.all(), required=False, empty_label="Todas"
    )
    conductor = forms.ModelChoiceField(
        queryset=Conductor.objects.select_related("usuario"), required=False, empty_label="Todos"
    )
    codigo = forms.CharField(required=False)
