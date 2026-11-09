from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.catalogo import servicios as catalogo
from apps.comun import PANEL, aplicar_errores, datos_formulario, disparar, es_htmx, responder
from apps.monitoreo.en_vivo import desconectar

from . import limite, restablecimiento
from .forms import (
    InicioSesionForm,
    NuevaContrasenaForm,
    SolicitudRestablecimientoForm,
    UsuarioAdministradorForm,
)
from .models import Rol
from .permisos import AdministradorRequeridoMixin
from .serializers import UsuarioAdministradorSerializer
from .tokens import borrar_cookies, emitir_tokens, poner_cookies, revocar_refresh

Usuario = get_user_model()

MENSAJE_LIMITE = "Demasiados intentos desde esta conexión. Espere unos minutos e intente de nuevo."


def _pagina_inicial(usuario):
    """A dónde va cada rol con la sesión abierta en la web (None: no usa la web).

    El conductor entra a la página de prueba del mapa en vivo; más adelante lo
    hará desde la app móvil.
    """
    if not usuario.is_authenticated:
        return None
    return {
        Rol.ADMINISTRADOR: reverse("monitoreo:panel"),
        Rol.CONDUCTOR: reverse("monitoreo:conductor"),
    }.get(usuario.rol)


def inicio(request):
    return redirect(_pagina_inicial(request.user) or "cuentas:login")


class InicioSesionView(View):
    """RF-01: inicio de sesión del panel web (emite JWT en cookie httpOnly)."""

    template_name = "cuentas/login.html"

    def get(self, request):
        destino = _pagina_inicial(request.user)
        if destino:
            return redirect(destino)
        return render(request, self.template_name, {"form": InicioSesionForm()})

    def post(self, request):
        form = InicioSesionForm(request.POST)
        if not limite.permitido(request, "login"):
            form.add_error(None, MENSAJE_LIMITE)
            return render(request, self.template_name, {"form": form}, status=429)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        usuario = authenticate(
            request,
            email=form.cleaned_data["email"].strip().lower(),
            password=form.cleaned_data["password"],
        )
        if usuario is None:
            form.add_error(None, "Correo o contraseña incorrectos, o el usuario está desactivado.")
            return render(request, self.template_name, {"form": form})
        if usuario.rol not in (Rol.ADMINISTRADOR, Rol.CONDUCTOR):
            form.add_error(
                None,
                "La plataforma web es para el administrador. Las instituciones "
                "usan la aplicación móvil de PAEGo.",
            )
            return render(request, self.template_name, {"form": form})
        if usuario.acepto_tratamiento_datos_en is None:
            if not form.cleaned_data["acepta_datos"]:
                form.add_error(
                    "acepta_datos",
                    "Debe aceptar la política de tratamiento de datos para continuar.",
                )
                return render(request, self.template_name, {"form": form, "pedir_datos": True})
            usuario.acepto_tratamiento_datos_en = timezone.now()
            usuario.save(update_fields=["acepto_tratamiento_datos_en"])
            registrar(
                usuario,
                Accion.ACEPTA_TRATAMIENTO_DATOS,
                "Aceptó la política de tratamiento de datos",
                request=request,
            )
        usuario.last_login = timezone.now()
        usuario.save(update_fields=["last_login"])
        registrar(usuario, Accion.INICIO_SESION, "Inicio de sesión (web)", request=request)
        destino = _pagina_inicial(usuario)
        siguiente = request.GET.get("next") or ""
        if (
            usuario.rol == Rol.ADMINISTRADOR
            and siguiente.startswith("/")
            and not siguiente.startswith("//")
        ):
            destino = siguiente
        respuesta = redirect(destino)
        poner_cookies(respuesta, emitir_tokens(usuario))
        return respuesta


@require_POST
def cerrar_sesion(request):
    """RF-02: revoca el refresh token y borra las cookies."""
    from django.conf import settings

    if request.user.is_authenticated:
        desconectar(request.user)
        registrar(request.user, Accion.CIERRE_SESION, "Cierre de sesión (web)", request=request)
    revocar_refresh(request.COOKIES.get(settings.JWT_COOKIE_REFRESH))
    request._jwt_cierre_sesion = True
    respuesta = redirect("cuentas:login")
    borrar_cookies(respuesta)
    messages.info(request, "Sesión cerrada.")
    return respuesta


class SolicitarRestablecimientoView(View):
    """RF-03: solicitar el enlace de restablecimiento."""

    template_name = "cuentas/restablecer.html"

    def get(self, request):
        return render(request, self.template_name, {"form": SolicitudRestablecimientoForm()})

    def post(self, request):
        form = SolicitudRestablecimientoForm(request.POST)
        if not limite.permitido(request, "restablecer"):
            form.add_error(None, MENSAJE_LIMITE)
            return render(request, self.template_name, {"form": form}, status=429)
        if form.is_valid():
            restablecimiento.solicitar(form.cleaned_data["email"])
            messages.success(
                request,
                "Si el correo está registrado, recibirá un enlace para restablecer la contraseña.",
            )
            return redirect("cuentas:login")
        return render(request, self.template_name, {"form": form})


class ConfirmarRestablecimientoView(View):
    template_name = "cuentas/restablecer_confirmar.html"

    def get(self, request, uidb64, token):
        valido = restablecimiento.usuario_desde_enlace(uidb64, token) is not None
        return render(
            request, self.template_name, {"form": NuevaContrasenaForm(), "valido": valido}
        )

    def post(self, request, uidb64, token):
        form = NuevaContrasenaForm(request.POST)
        if form.is_valid():
            try:
                restablecimiento.confirmar(
                    uidb64, token, form.cleaned_data["nueva_password"], request=request
                )
            except DjangoValidationError as exc:
                for mensaje in exc.messages:
                    form.add_error("nueva_password", mensaje)
            except ValidationError:
                return render(request, self.template_name, {"form": form, "valido": False})
            else:
                messages.success(request, "Contraseña actualizada. Ya puede iniciar sesión.")
                return redirect("cuentas:login")
        return render(request, self.template_name, {"form": form, "valido": True})


class UsuarioListaView(AdministradorRequeridoMixin, View):
    """RF-04 / RF-05: todos los usuarios con su rol."""

    def get(self, request):
        usuarios = Usuario.objects.all().order_by("rol", "first_name", "last_name")
        rol = request.GET.get("rol")
        texto = request.GET.get("q", "").strip()
        if rol:
            usuarios = usuarios.filter(rol=rol)
        if texto:
            usuarios = usuarios.filter(
                Q(email__icontains=texto)
                | Q(first_name__icontains=texto)
                | Q(last_name__icontains=texto)
            )
        pagina = Paginator(usuarios, 30).get_page(request.GET.get("pagina"))
        parametros = request.GET.copy()
        parametros.pop("pagina", None)
        return responder(
            request,
            "cuentas/usuarios.html",
            {
                "pagina": pagina,
                "roles": Rol.choices,
                "rol": rol,
                "q": texto,
                "parametros": parametros.urlencode(),
            },
            {"resultados": "cuentas/_usuarios_tabla.html"},
        )


class UsuarioFormularioView(AdministradorRequeridoMixin, View):
    """Crear o editar administradores (los demás roles tienen su módulo)."""

    template_name = "cuentas/usuario_form.html"

    def _usuario(self, pk):
        if pk is None:
            return None
        return get_object_or_404(Usuario, pk=pk, rol=Rol.ADMINISTRADOR)

    def get(self, request, pk=None):
        usuario = self._usuario(pk)
        inicial = {}
        if usuario:
            inicial = {
                c: getattr(usuario, c) for c in ("email", "first_name", "last_name", "telefono")
            }
        return self._responder(request, UsuarioAdministradorForm(initial=inicial), usuario)

    def _responder(self, request, form, usuario):
        return responder(
            request,
            self.template_name,
            {"form": form, "objeto": usuario},
            {PANEL: "cuentas/_usuario_form.html"},
        )

    def post(self, request, pk=None):
        usuario = self._usuario(pk)
        form = UsuarioAdministradorForm(request.POST)
        if form.is_valid():
            serializer = UsuarioAdministradorSerializer(
                instance=usuario, data=datos_formulario(form), partial=usuario is not None
            )
            try:
                serializer.is_valid(raise_exception=True)
            except ValidationError as exc:
                aplicar_errores(form, exc)
            else:
                guardado = serializer.save()
                registrar(
                    request.user,
                    Accion.EDITAR if usuario else Accion.CREAR,
                    f"Usuario: {guardado}",
                    objeto=guardado,
                    request=request,
                )
                messages.success(request, f"Administrador «{guardado}» guardado.")
                if es_htmx(request):
                    return disparar(
                        render(request, "_avisos.html", {"oob": True}),
                        "cerrar-panel",
                        "usuarios-actualizados",
                    )
                return redirect("cuentas:usuarios")
        return self._responder(request, form, usuario)


@require_POST
def cambiar_estado_usuario(request, pk):
    """RF-04: desactivar o reactivar cualquier usuario."""
    if not request.user.is_authenticated or request.user.rol != Rol.ADMINISTRADOR:
        return redirect("cuentas:login")
    usuario = get_object_or_404(Usuario, pk=pk)
    try:
        catalogo.cambiar_activo(request.user, usuario, not usuario.is_active, request=request)
        messages.success(
            request,
            f"Usuario «{usuario}» {'activado' if usuario.is_active else 'desactivado'}.",
        )
    except PermissionDenied as exc:
        messages.error(request, str(exc.detail))
    if es_htmx(request):
        return disparar(render(request, "_avisos.html", {"oob": True}), "usuarios-actualizados")
    return redirect(request.POST.get("volver") or "cuentas:usuarios")
