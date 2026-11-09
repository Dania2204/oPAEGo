"""Panel web: instituciones, conductores, vehículos y responsables (RF-07 a RF-12).

Una configuración por módulo y vistas genéricas comunes.
"""

from dataclasses import dataclass, field

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from rest_framework.exceptions import PermissionDenied

from apps.comun import (
    PANEL,
    datos_formulario,
    disparar,
    es_htmx,
    nuevo_uuid,
    operar,
    responder,
)
from apps.cuentas.permisos import AdministradorRequeridoMixin

from . import servicios
from .forms import ConductorForm, InstitucionForm, ResponsableForm, VehiculoForm
from .models import Conductor, Institucion, ResponsableRecepcion, Vehiculo


@dataclass
class Modulo:
    clave: str
    modelo: type
    form: type
    titulo: str
    singular: str
    columnas: list
    busqueda: list
    select_related: list = field(default_factory=list)
    con_mapa: bool = False
    con_usuario: bool = False

    def inicial(self, objeto):
        datos = {}
        for nombre in self.form.base_fields:
            if nombre == "password":
                continue
            if self.con_usuario and nombre in ("email", "first_name", "last_name"):
                datos[nombre] = getattr(objeto.usuario, nombre)
            else:
                valor = getattr(objeto, nombre, None)
                datos[nombre] = getattr(valor, "pk", valor)
        return datos


MODULOS = {
    "instituciones": Modulo(
        "institucion",
        Institucion,
        InstitucionForm,
        "Instituciones educativas",
        "institución",
        [
            ("nombre", "Nombre"),
            ("sede", "Sede"),
            ("direccion", "Dirección"),
            ("contacto_telefono", "Teléfono"),
        ],
        ["nombre", "sede", "direccion"],
        con_mapa=True,
    ),
    "conductores": Modulo(
        "conductor",
        Conductor,
        ConductorForm,
        "Conductores",
        "conductor",
        [
            ("usuario.get_full_name", "Nombre"),
            ("numero_documento", "Documento"),
            ("telefono", "Teléfono"),
            ("usuario.email", "Correo"),
        ],
        ["usuario__first_name", "usuario__last_name", "numero_documento"],
        select_related=["usuario"],
        con_usuario=True,
    ),
    "vehiculos": Modulo(
        "vehiculo",
        Vehiculo,
        VehiculoForm,
        "Vehículos",
        "vehículo",
        [
            ("placa", "Placa"),
            ("tipo", "Tipo"),
            ("capacidad_kg", "Capacidad (kg)"),
            ("conductor", "Conductor"),
        ],
        ["placa", "tipo"],
        select_related=["conductor__usuario"],
    ),
    "responsables": Modulo(
        "responsable",
        ResponsableRecepcion,
        ResponsableForm,
        "Responsables de recepción",
        "responsable",
        [
            ("usuario.get_full_name", "Nombre"),
            ("institucion", "Institución"),
            ("cargo", "Cargo"),
            ("usuario.email", "Correo"),
        ],
        ["usuario__first_name", "usuario__last_name", "cargo", "institucion__nombre"],
        select_related=["usuario", "institucion"],
        con_usuario=True,
    ),
}


def _valor(objeto, ruta):
    for parte in ruta.split("."):
        objeto = getattr(objeto, parte, None)
        if callable(objeto):
            objeto = objeto()
        if objeto is None:
            return ""
    return objeto


def guardado_en_panel(request, evento):
    """Respuesta HTMX tras guardar desde el panel: lo cierra, muestra el aviso
    y pide a la lista que se recargue."""
    respuesta = render(request, "_avisos.html", {"oob": True})
    return disparar(respuesta, "cerrar-panel", evento)


class ListaView(AdministradorRequeridoMixin, View):
    def get(self, request, modulo):
        cfg = MODULOS[modulo]
        objetos = cfg.modelo.objects.select_related(*cfg.select_related)
        texto = request.GET.get("q", "").strip()
        estado = request.GET.get("estado", "activos")
        if texto:
            filtro = Q()
            for campo in cfg.busqueda:
                filtro |= Q(**{f"{campo}__icontains": texto})
            objetos = objetos.filter(filtro)
        if estado == "activos":
            objetos = objetos.filter(activo=True)
        elif estado == "inactivos":
            objetos = objetos.filter(activo=False)
        pagina = Paginator(objetos, 30).get_page(request.GET.get("pagina"))
        filas = [
            {"objeto": o, "celdas": [_valor(o, ruta) for ruta, _ in cfg.columnas]} for o in pagina
        ]
        parametros = request.GET.copy()
        parametros.pop("pagina", None)
        return responder(
            request,
            "catalogo/lista.html",
            {
                "cfg": cfg,
                "modulo": modulo,
                "pagina": pagina,
                "filas": filas,
                "q": texto,
                "estado": estado,
                "parametros": parametros.urlencode(),
            },
            {"resultados": "catalogo/_tabla.html"},
        )


class FormularioView(AdministradorRequeridoMixin, View):
    def _responder(self, request, cfg, modulo, form, objeto, uuid_cliente):
        contexto = {
            "cfg": cfg,
            "modulo": modulo,
            "form": form,
            "objeto": objeto,
            "uuid_cliente": uuid_cliente,
            "tipo_operacion": f"{cfg.clave}.{'editar' if objeto else 'crear'}",
        }
        return responder(
            request, "catalogo/formulario.html", contexto, {PANEL: "catalogo/_formulario.html"}
        )

    def get(self, request, modulo, pk=None):
        cfg = MODULOS[modulo]
        objeto = get_object_or_404(cfg.modelo, pk=pk) if pk else None
        form = cfg.form(initial=cfg.inicial(objeto) if objeto else None)
        return self._responder(request, cfg, modulo, form, objeto, nuevo_uuid())

    def post(self, request, modulo, pk=None):
        cfg = MODULOS[modulo]
        objeto = get_object_or_404(cfg.modelo, pk=pk) if pk else None
        form = cfg.form(request.POST)
        if form.is_valid():
            datos = datos_formulario(form)
            if objeto:
                datos["id"] = objeto.pk
            tipo = f"{cfg.clave}.{'editar' if objeto else 'crear'}"
            if operar(request, form, tipo, datos) is not None:
                messages.success(request, f"{cfg.singular.capitalize()} guardado correctamente.")
                if es_htmx(request):
                    return guardado_en_panel(request, "catalogo-actualizado")
                return redirect("catalogo:lista", modulo=modulo)
        return self._responder(request, cfg, modulo, form, objeto, request.POST.get("uuid_cliente"))


class CambiarEstadoView(AdministradorRequeridoMixin, View):
    """Desactivar / reactivar (RF-08, RF-10). Nunca se borra: se conserva el historial."""

    def post(self, request, modulo, pk):
        cfg = MODULOS[modulo]
        objeto = get_object_or_404(cfg.modelo, pk=pk)
        try:
            servicios.cambiar_activo(request.user, objeto, not objeto.activo, request=request)
            messages.success(
                request, f"«{objeto}» {'activado' if objeto.activo else 'desactivado'}."
            )
        except PermissionDenied as exc:
            messages.error(request, str(exc.detail))
        if es_htmx(request):
            return disparar(render(request, "_avisos.html", {"oob": True}), "catalogo-actualizado")
        return redirect("catalogo:lista", modulo=modulo)
