"""Formularios del panel. Los nombres de campo son los de los serializers de
la API, que son la única fuente de validación."""

from django import forms

from .models import Conductor, Institucion


class InstitucionForm(forms.Form):
    nombre = forms.CharField(max_length=200)
    sede = forms.CharField(max_length=120, initial="Principal")
    direccion = forms.CharField(label="Dirección", max_length=255)
    latitud = forms.DecimalField(max_digits=9, decimal_places=6, help_text="Clic en el mapa")
    longitud = forms.DecimalField(max_digits=9, decimal_places=6)
    contacto_nombre = forms.CharField(label="Nombre de contacto", max_length=150, required=False)
    contacto_telefono = forms.CharField(label="Teléfono de contacto", max_length=30, required=False)
    contacto_email = forms.EmailField(label="Correo de contacto", required=False)


class _UsuarioForm(forms.Form):
    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo (usuario de la app móvil)")
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput,
        required=False,
        help_text="Obligatoria al crear. Al editar, déjela vacía para conservar la actual.",
    )


class ConductorForm(_UsuarioForm):
    tipo_documento = forms.ChoiceField(choices=Conductor.TipoDocumento.choices)
    numero_documento = forms.CharField(label="Número de documento", max_length=20)
    telefono = forms.CharField(label="Teléfono", max_length=30)
    numero_licencia = forms.CharField(label="Número de licencia", max_length=30, required=False)


class ResponsableForm(_UsuarioForm):
    institucion = forms.ModelChoiceField(
        label="Institución",
        queryset=Institucion.objects.filter(activo=True),
        empty_label="Elegir institución…",
    )
    cargo = forms.CharField(max_length=100, help_text="Rector, coordinador, almacenista…")
    telefono = forms.CharField(label="Teléfono", max_length=30, required=False)


class VehiculoForm(forms.Form):
    placa = forms.CharField(max_length=10)
    tipo = forms.CharField(max_length=50, help_text="Camión, furgón, camioneta…")
    capacidad_kg = forms.DecimalField(label="Capacidad (kg)", max_digits=8, decimal_places=2)
    conductor = forms.ModelChoiceField(
        queryset=Conductor.objects.filter(activo=True).select_related("usuario"),
        required=False,
        empty_label="Sin asignar",
    )
