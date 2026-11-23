"""Formularios del panel: agregar un estudiante y actualizar desde SIMAT."""

from django import forms
from django.core.validators import RegexValidator

from apps.catalogo.simat import GRADOS, JORNADAS, TIPOS_DOCUMENTO

from .importacion import GRADOS_PAE

MAX_ARCHIVO_MB = 25


class EstudianteForm(forms.Form):
    """Identidad mínima (Ley 1581): documento, nombre y curso. Nada más."""

    tipo_documento = forms.ChoiceField(
        label="Tipo de documento",
        choices=[(c, e) for c, e in TIPOS_DOCUMENTO.items()],
        initial="2",
    )
    numero_documento = forms.CharField(
        label="Número de documento",
        max_length=20,
        validators=[RegexValidator(r"^[0-9A-Za-z-]{4,20}$", "Escriba solo números (o letras).")],
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
    )
    nombres = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"autocomplete": "off"}))
    apellidos = forms.CharField(
        max_length=100, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    grado = forms.ChoiceField(
        choices=[(c, e) for c, e in GRADOS.items() if c in GRADOS_PAE],
    )
    grupo = forms.CharField(
        max_length=10, help_text="Como aparece en SIMAT, p. ej. 701.", required=True
    )
    jornada = forms.ChoiceField(choices=[("", "—"), *JORNADAS.items()], required=False)

    def clean_nombres(self):
        return " ".join(self.cleaned_data["nombres"].split()).title()

    def clean_apellidos(self):
        return " ".join(self.cleaned_data["apellidos"].split()).title()

    def clean_grupo(self):
        return self.cleaned_data["grupo"].strip().upper()


class ImportarForm(forms.Form):
    archivo = forms.FileField(
        label="Anexo 6A de SIMAT (.xlsx)",
        help_text="El mismo archivo de matrícula de la Secretaría; puede traer a todas las "
        "instituciones del municipio.",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        ),
    )
    codigo_dane = forms.CharField(
        label="Código DANE de la institución",
        max_length=20,
        validators=[RegexValidator(r"^\d{6,20}$", "El código DANE tiene solo números.")],
        help_text="Con él se toman del archivo solo los estudiantes de esta institución.",
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Suba el archivo en formato Excel (.xlsx).")
        if archivo.size > MAX_ARCHIVO_MB * 1024 * 1024:
            raise forms.ValidationError(f"El archivo supera {MAX_ARCHIVO_MB} MB.")
        return archivo
