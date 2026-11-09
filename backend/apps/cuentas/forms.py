from django import forms


class InicioSesionForm(forms.Form):
    # Sin mayúscula ni corrección automática: en el celular alteran el correo y la contraseña.
    email = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )
    acepta_datos = forms.BooleanField(
        required=False,
        label="Acepto la política de tratamiento de datos personales (Ley 1581 de 2012).",
    )


class SolicitudRestablecimientoForm(forms.Form):
    email = forms.EmailField(label="Correo registrado")


class NuevaContrasenaForm(forms.Form):
    nueva_password = forms.CharField(label="Nueva contraseña", widget=forms.PasswordInput)
    confirmacion = forms.CharField(label="Confirme la contraseña", widget=forms.PasswordInput)

    def clean(self):
        datos = super().clean()
        if datos.get("nueva_password") != datos.get("confirmacion"):
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return datos


class UsuarioAdministradorForm(forms.Form):
    """RF-04: los nombres coinciden con UsuarioAdministradorSerializer."""

    email = forms.EmailField(label="Correo")
    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    telefono = forms.CharField(label="Teléfono", max_length=30, required=False)
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput,
        required=False,
        help_text="Obligatoria al crear. Al editar, déjela vacía para conservar la actual.",
    )
