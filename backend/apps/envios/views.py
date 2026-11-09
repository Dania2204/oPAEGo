"""Panel web: gestión de envíos del administrador (RF-13 a RF-18, RF-34, RF-35).

El detalle, la creación y las acciones se muestran en el panel lateral (HTMX);
sin JavaScript las mismas URL funcionan como páginas completas.
"""

import json
import uuid
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.catalogo.models import Conductor, Institucion, Vehiculo
from apps.comun import (
    PANEL,
    datos_formulario,
    destino_htmx,
    disparar,
    es_htmx,
    nuevo_uuid,
    operar,
    responder,
)
from apps.cuentas.permisos import AdministradorRequeridoMixin
from apps.sincronizacion.operaciones import ejecutar

from .api import queryset_por_rol
from .estados import Estado
from .forms import UNIDADES, EnvioForm, FiltroEnviosForm, MotivoForm, ReasignarForm
from .models import Envio

VISTAS = [
    ("todos", "Todos"),
    ("hoy", "Hoy"),
    ("proximos", "Próximos"),
    ("en_ruta", "En ruta"),
    ("novedad", "Con novedad"),
]


def _filtrar_vista(envios, vista):
    hoy = timezone.localdate()
    if vista == "hoy":
        return envios.filter(programado_para__date=hoy)
    if vista == "proximos":
        return envios.filter(programado_para__date__gt=hoy, estado=Estado.ASIGNADO).order_by(
            "programado_para"
        )
    if vista == "en_ruta":
        return envios.filter(estado=Estado.EN_TRANSITO)
    if vista == "novedad":
        return envios.filter(estado=Estado.CON_NOVEDAD)
    return envios


class EnvioListaView(AdministradorRequeridoMixin, View):
    """RF-17: listar y filtrar envíos por fecha, estado, institución y conductor."""

    def get(self, request):
        vista = request.GET.get("vista", "todos")
        if vista not in dict(VISTAS):
            vista = "todos"
        filtros = FiltroEnviosForm(request.GET or None)
        base = queryset_por_rol(request.user).order_by("-programado_para")
        if filtros.is_valid():
            d = filtros.cleaned_data
            if d["fecha_desde"]:
                base = base.filter(programado_para__date__gte=d["fecha_desde"])
            if d["fecha_hasta"]:
                base = base.filter(programado_para__date__lte=d["fecha_hasta"])
            if d["estado"]:
                base = base.filter(estado=d["estado"])
            if d["institucion"]:
                base = base.filter(institucion=d["institucion"])
            if d["conductor"]:
                base = base.filter(conductor=d["conductor"])
            if d["codigo"]:
                base = base.filter(codigo__icontains=d["codigo"])
        pestanas = [
            (clave, nombre, _filtrar_vista(base, clave).count()) for clave, nombre in VISTAS
        ]
        pagina = Paginator(_filtrar_vista(base, vista), 30).get_page(request.GET.get("pagina"))
        parametros = request.GET.copy()
        parametros.pop("pagina", None)
        sin_vista = parametros.copy()
        sin_vista.pop("vista", None)
        contexto = {
            "pagina": pagina,
            "filtros": filtros,
            "vista": vista,
            "pestanas": pestanas,
            "parametros": parametros.urlencode(),
            "parametros_sin_vista": sin_vista.urlencode(),
            "hay_filtros": any(v for k, v in request.GET.items() if k not in ("vista", "pagina")),
            "es_parcial": destino_htmx(request) == "resultados",
        }
        return responder(
            request, "envios/lista.html", contexto, {"resultados": "envios/_resultados.html"}
        )


def _contexto_detalle(envio):
    ruta = [
        [float(lat), float(lng)]
        for lat, lng in envio.ubicaciones.order_by("ocurrido_en").values_list("latitud", "longitud")
    ]
    evidencia = getattr(envio, "evidencia", None)
    mapa = {
        "ruta": ruta,
        "destino": [float(envio.institucion.latitud), float(envio.institucion.longitud)],
        "destino_nombre": str(envio.institucion),
        "salida": (
            [float(envio.salida_latitud), float(envio.salida_longitud)]
            if envio.salida_latitud is not None
            else None
        ),
        "entrega": (
            [float(evidencia.latitud), float(evidencia.longitud)]
            if evidencia and evidencia.latitud is not None
            else None
        ),
    }
    return {
        "envio": envio,
        "historial": envio.registros_auditoria.select_related("usuario").order_by(
            "ocurrido_en", "id"
        ),
        "evidencia": evidencia,
        "novedades": envio.novedades.select_related("reportado_por"),
        "mapa_json": json.dumps(mapa),
        "puntos_ruta": len(ruta),
        "puede_modificar": envio.estado == Estado.ASIGNADO and not envio.salida_en,
        "puede_cerrar": envio.estado == Estado.EN_TRANSITO,
        "form_reasignar": ReasignarForm(
            initial={"conductor": envio.conductor_id, "vehiculo": envio.vehiculo_id}
        ),
        "form_motivo": MotivoForm(),
        "uuid_reasignar": nuevo_uuid(),
        "uuid_cancelar": nuevo_uuid(),
        "uuid_cerrar": nuevo_uuid(),
    }


def _responder_detalle(request, envio, eventos=()):
    envio = queryset_por_rol(request.user).get(pk=envio.pk)
    contexto = _contexto_detalle(envio)
    contexto["oob_avisos"] = es_htmx(request)
    respuesta = responder(request, "envios/detalle.html", contexto, {PANEL: "envios/_detalle.html"})
    if eventos:
        disparar(respuesta, *eventos)
    return respuesta


class EnvioDetalleView(AdministradorRequeridoMixin, View):
    """Detalle con historial (RF-34) y ruta recorrida (RF-35)."""

    def get(self, request, pk):
        envio = get_object_or_404(queryset_por_rol(request.user), pk=pk)
        return _responder_detalle(request, envio)


def _inicial_desde(envio, duplicar=False):
    programado = timezone.localtime(envio.programado_para)
    if duplicar:
        # La copia se propone para el siguiente día hábil, a la misma hora.
        dias = 3 if programado.weekday() == 4 else 2 if programado.weekday() == 5 else 1
        programado = max(programado, timezone.localtime()) + timedelta(days=dias)
        programado = programado.replace(
            hour=timezone.localtime(envio.programado_para).hour,
            minute=timezone.localtime(envio.programado_para).minute,
        )
    inicial = {
        "institucion": envio.institucion_id,
        "programado_para": programado,
        "conductor": envio.conductor_id,
        "vehiculo": envio.vehiculo_id,
        "observaciones": envio.observaciones,
    }
    items = [
        {"producto": i.producto, "cantidad": i.cantidad, "unidad": i.unidad}
        for i in envio.items.all()
    ]
    return inicial, items


class EnvioFormularioView(AdministradorRequeridoMixin, View):
    """RF-13 a RF-15 (crear y asignar), RF-16 (modificar antes de la salida) y
    «Duplicar envío» (`?duplicar=<id>`)."""

    def _responder(self, request, form, envio, items, uuid_cliente, duplicado=None):
        contexto = {
            "form": form,
            "objeto": envio,
            "items": items,
            "unidades": UNIDADES,
            "uuid_cliente": uuid_cliente,
            "duplicado": duplicado,
            "tipo_operacion": "envio.editar" if envio else "envio.crear",
            # RF-14: sugerir las raciones según la matrícula (beneficiarios) de la
            # institución elegida. Mapa id→beneficiarios para el editor de alimentos.
            "raciones_json": json.dumps(
                {
                    str(pk): total
                    for pk, total in Institucion.objects.filter(
                        activo=True, beneficiarios_total__gt=0
                    ).values_list("pk", "beneficiarios_total")
                }
            ),
        }
        return responder(
            request, "envios/formulario.html", contexto, {PANEL: "envios/_formulario.html"}
        )

    def get(self, request, pk=None):
        envio = get_object_or_404(Envio, pk=pk) if pk else None
        duplicado = None
        if envio:
            if envio.estado != Estado.ASIGNADO or envio.salida_en:
                messages.error(request, "Solo se puede modificar un envío antes de su salida.")
                return (
                    _responder_detalle(request, envio)
                    if es_htmx(request)
                    else redirect("envios:detalle", pk=envio.pk)
                )
            inicial, items = _inicial_desde(envio)
        elif request.GET.get("duplicar"):
            duplicado = get_object_or_404(Envio, pk=request.GET["duplicar"])
            inicial, items = _inicial_desde(duplicado, duplicar=True)
        else:
            inicial, items = {}, []
        form = EnvioForm(initial=inicial, edicion=envio is not None)
        return self._responder(request, form, envio, items, nuevo_uuid(), duplicado)

    def post(self, request, pk=None):
        envio = get_object_or_404(Envio, pk=pk) if pk else None
        form = EnvioForm(request.POST, edicion=envio is not None)
        items = form.items()
        if form.is_valid():
            datos = datos_formulario(form)
            datos["programado_para"] = form.cleaned_data["programado_para"].isoformat()
            datos["items"] = items
            if envio:
                datos["envio"] = envio.pk
            respuesta = operar(request, form, "envio.editar" if envio else "envio.crear", datos)
            if respuesta is not None:
                guardado = Envio.objects.get(pk=respuesta["id"])
                messages.success(
                    request,
                    f"Envío {guardado.codigo} {'modificado' if envio else 'creado y asignado'}.",
                )
                if es_htmx(request):
                    r = _responder_detalle(request, guardado, ["envios-actualizados"])
                    r["HX-Push-Url"] = reverse("envios:detalle", args=[guardado.pk])
                    return r
                return redirect("envios:detalle", pk=guardado.pk)
        return self._responder(request, form, envio, items, request.POST.get("uuid_cliente"))


class _AccionMotivoView(AdministradorRequeridoMixin, View):
    """Reasignar, cancelar y cerrar con novedad desde el detalle (RF-16)."""

    tipo = ""
    form_class = MotivoForm
    exito = ""

    def post(self, request, pk):
        envio = get_object_or_404(Envio, pk=pk)
        form = self.form_class(request.POST)
        ok = False
        if form.is_valid():
            datos = datos_formulario(form)
            datos["envio"] = envio.pk
            ok = operar(request, form, self.tipo, datos) is not None
        if ok:
            messages.success(request, self.exito.format(codigo=envio.codigo))
        else:
            for errores in form.errors.values():
                for texto in errores:
                    messages.error(request, texto)
        if es_htmx(request):
            return _responder_detalle(request, envio, ["envios-actualizados"] if ok else [])
        return redirect("envios:detalle", pk=pk)


class ReasignarView(_AccionMotivoView):
    tipo = "envio.reasignar"
    form_class = ReasignarForm
    exito = "Envío {codigo} reasignado."


class CancelarView(_AccionMotivoView):
    tipo = "envio.cancelar"
    exito = "Envío {codigo} cancelado."


class CerrarConNovedadView(_AccionMotivoView):
    tipo = "envio.cerrar_con_novedad"
    exito = "Envío {codigo} cerrado con novedad."


# --------------------------------------------------------------------------
# Programar envíos del día en lote (mejora de flujo de RF-13 a RF-15)
# --------------------------------------------------------------------------
def _ultimas_asignaciones():
    """Conductor y vehículo usados la última vez para cada institución."""
    asignaciones = {}
    for envio in Envio.objects.exclude(estado=Estado.CANCELADO).order_by("-programado_para")[:500]:
        asignaciones.setdefault(envio.institucion_id, (envio.conductor_id, envio.vehiculo_id))
    return asignaciones


def _siguiente_dia_habil():
    dia = timezone.localdate() + timedelta(days=1)
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


class ProgramarView(AdministradorRequeridoMixin, View):
    """Crea en un paso los envíos del día para varias instituciones con el mismo
    menú. Cada envío pasa por la misma operación idempotente que la API."""

    template_name = "envios/programar.html"

    def _filas(self, valores=None):
        asignaciones = _ultimas_asignaciones()
        valores = valores or {}
        filas = []
        for institucion in Institucion.objects.filter(activo=True).order_by("nombre", "sede"):
            conductor, vehiculo = asignaciones.get(institucion.pk, (None, None))
            filas.append(
                {
                    "institucion": institucion,
                    "seleccionada": str(institucion.pk) in valores.get("instituciones", []),
                    "conductor": str(valores.get(f"conductor_{institucion.pk}", conductor or "")),
                    "vehiculo": str(valores.get(f"vehiculo_{institucion.pk}", vehiculo or "")),
                    "error": valores.get("errores", {}).get(institucion.pk),
                }
            )
        return filas

    def _contexto(self, filas, fecha, hora, items, uuid_lote, observaciones="", errores=None):
        return {
            "filas": filas,
            "conductores": Conductor.objects.filter(activo=True, usuario__is_active=True)
            .select_related("usuario")
            .order_by("usuario__first_name"),
            "vehiculos": Vehiculo.objects.filter(activo=True).order_by("placa"),
            "fecha": fecha,
            "hora": hora,
            "items": items,
            "unidades": UNIDADES,
            "uuid_lote": uuid_lote,
            "observaciones": observaciones,
            "errores": errores or [],
        }

    def get(self, request):
        contexto = self._contexto(
            self._filas(), _siguiente_dia_habil().isoformat(), "07:00", [], nuevo_uuid()
        )
        return responder(request, self.template_name, contexto)

    def post(self, request):
        p = request.POST
        seleccion = p.getlist("instituciones")
        items = EnvioForm(p).items()
        errores = []
        programado = None
        try:
            programado = timezone.make_aware(
                datetime.combine(
                    datetime.strptime(p.get("fecha", ""), "%Y-%m-%d").date(),
                    time.fromisoformat(p.get("hora", "")),
                )
            )
        except ValueError:
            errores.append("Indique una fecha y una hora válidas.")
        if not seleccion:
            errores.append("Seleccione al menos una institución.")
        if not items:
            errores.append("Registre al menos un alimento del menú.")

        creados, errores_por_institucion = [], {}
        if not errores:
            lote = uuid.UUID(p.get("uuid_lote") or nuevo_uuid())
            for institucion_id in seleccion:
                datos = {
                    "institucion": institucion_id,
                    "conductor": p.get(f"conductor_{institucion_id}"),
                    "vehiculo": p.get(f"vehiculo_{institucion_id}") or None,
                    "programado_para": programado.isoformat(),
                    "observaciones": p.get("observaciones", ""),
                    "items": items,
                }
                resultado, respuesta = ejecutar(
                    request.user,
                    "envio.crear",
                    datos,
                    # Un uuid por institución derivado del lote: reenviar el
                    # formulario no duplica envíos.
                    uuid_cliente=uuid.uuid5(lote, str(institucion_id)),
                    request=request,
                )
                if resultado in ("ok", "duplicado"):
                    creados.append(respuesta.get("codigo") or respuesta.get("id"))
                else:
                    errores_por_institucion[int(institucion_id)] = _texto_error(respuesta)

        if not errores and not errores_por_institucion:
            messages.success(
                request,
                f"Se programaron {len(creados)} envío{'s' if len(creados) != 1 else ''} "
                f"para el {programado:%d/%m/%Y} a las {programado:%H:%M}.",
            )
            fecha = timezone.localdate(programado).isoformat()
            return redirect(f"{reverse('envios:lista')}?fecha_desde={fecha}&fecha_hasta={fecha}")

        if creados:
            messages.success(request, f"Se programaron {len(creados)} envíos; revise los demás.")
        valores = {k: v for k, v in p.items()}
        valores["instituciones"] = [
            i for i in seleccion if int(i) in errores_por_institucion
        ] or seleccion
        valores["errores"] = errores_por_institucion
        contexto = self._contexto(
            self._filas(valores),
            p.get("fecha", ""),
            p.get("hora", ""),
            items,
            p.get("uuid_lote") or nuevo_uuid(),
            p.get("observaciones", ""),
            errores,
        )
        return responder(request, self.template_name, contexto, status=200)


def _texto_error(respuesta):
    detalle = respuesta.get("detalle", respuesta)
    if isinstance(detalle, dict):
        return " ".join(f"{v[0] if isinstance(v, list) else v}" for v in detalle.values())
    return str(detalle)
