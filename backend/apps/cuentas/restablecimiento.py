"""RF-03: restablecer la contraseña de forma segura.

Se envía al correo un enlace con un token de un solo uso (el token se
invalida al cambiar la contraseña) y con vencimiento (PASSWORD_RESET_TIMEOUT).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar


def solicitar(email):
    """Envía el enlace si el correo existe. No revela si existe o no."""
    usuario = get_user_model().objects.filter(email=email.strip().lower(), is_active=True).first()
    if usuario is None:
        return
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    enlace = settings.URL_PUBLICA.rstrip("/") + reverse(
        "cuentas:restablecer_confirmar", kwargs={"uidb64": uid, "token": token}
    )
    send_mail(
        "PAEGo — Restablecer contraseña",
        (
            f"Hola {usuario.get_full_name()},\n\n"
            "Recibimos una solicitud para restablecer su contraseña de PAEGo.\n"
            f"Ingrese al siguiente enlace para definir una nueva:\n\n{enlace}\n\n"
            "Si usted no hizo la solicitud, ignore este mensaje."
        ),
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
    )


def usuario_desde_enlace(uidb64, token):
    try:
        pk = force_str(urlsafe_base64_decode(uidb64))
        usuario = get_user_model().objects.get(pk=pk, is_active=True)
    except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
        return None
    if not default_token_generator.check_token(usuario, token):
        return None
    return usuario


def confirmar(uidb64, token, nueva_password, request=None):
    usuario = usuario_desde_enlace(uidb64, token)
    if usuario is None:
        raise ValidationError({"token": "El enlace no es válido o ya venció."})
    validate_password(nueva_password, usuario)
    usuario.set_password(nueva_password)
    usuario.save(update_fields=["password"])
    registrar(
        usuario,
        Accion.RESTABLECER_CONTRASENA,
        "Contraseña restablecida",
        objeto=usuario,
        request=request,
    )
    return usuario
