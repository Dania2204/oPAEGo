"""Panel web del administrador: entrega del PAE por estudiante.

El supervisor trabaja en la app móvil; aquí el administrador ve la cobertura del
día por curso y por estudiante, registra o revoca la autorización biométrica que
entrega el acudiente en papel y exporta la lista del día.
"""

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from openpyxl import Workbook

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.catalogo.models import Institucion
from apps.comun import PANEL, disparar, es_htmx, nuevo_uuid, operar, responder
from apps.cuentas.permisos import AdministradorRequeridoMixin

from . import consultas
from .models import Estudiante


class AutorizacionForm(forms.Form):
    acudiente_nombre = forms.CharField(label="Nombre del acudiente", max_length=150)
    acudiente_documento = forms.CharField(label="Documento del acudiente", max_length=20)
    parentesco = forms.CharField(max_length=50, help_text="Madre, padre, abuela, tutor…")
    confirmo = forms.BooleanField(
        label="Tengo la autorización firmada por el acudiente (previa, expresa e informada).",
    )


class RevocarForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 2})
    )


def _fecha(request):
    return parse_date(request.GET.get("fecha") or "") or timezone.localdate()


def _filtros(request):
    """Institución, fecha y curso elegidos (con valores por defecto razonables)."""
    instituciones = list(
        Institucion.objects.filter(estudiantes__activo=True).distinct().order_by("nombre")
    )
    institucion = None
    if request.GET.get("institucion"):
        institucion = next(
            (i for i in instituciones if str(i.pk) == request.GET["institucion"]), None
        )
    if institucion is None and instituciones:
        institucion = instituciones[0]
    return {
        "instituciones": instituciones,
        "institucion": institucion,
        "fecha": _fecha(request),
        "grado": request.GET.get("grado", ""),
        "grupo": request.GET.get("grupo", ""),
    }


def _estudiantes(institucion):
    return Estudiante.objects.filter(institucion=institucion)


class EstudiantesView(AdministradorRequeridoMixin, View):
    def get(self, request):
        f = _filtros(request)
        contexto = {**f, "hoy": timezone.localdate()}
        if f["institucion"] is not None:
            base = _estudiantes(f["institucion"])
            contexto["cobertura"] = consultas.cobertura(base, f["fecha"])
            contexto["cursos"] = consultas.resumen_cursos(base, f["fecha"])
            contexto["con_rostro"] = (
                base.filter(activo=True, plantillas__isnull=False).distinct().count()
            )
            if f["grado"]:
                contexto["estudiantes"] = consultas.con_estado_del_dia(
                    consultas.estudiantes_del_curso(base, f["grado"], f["grupo"]), f["fecha"]
                )
                contexto["curso_elegido"] = next(
                    (
                        c
                        for c in contexto["cursos"]
                        if c["grado"] == f["grado"] and c["grupo"] == f["grupo"]
                    ),
                    None,
                )
        return responder(
            request,
            "estudiantes/lista.html",
            contexto,
            {"resultados": "estudiantes/_contenido.html"},
        )


class EstudianteDetalleView(AdministradorRequeridoMixin, View):
    def _responder(self, request, estudiante, form_autorizar=None, form_revocar=None):
        contexto = {
            "estudiante": estudiante,
            "autorizacion": getattr(estudiante, "autorizacion", None),
            "num_plantillas": estudiante.plantillas.count(),
            "entregas": estudiante.entregas.select_related("supervisor")[:30],
            "form_autorizar": form_autorizar or AutorizacionForm(),
            "form_revocar": form_revocar or RevocarForm(),
            "uuid_cliente": nuevo_uuid(),
        }
        return responder(
            request,
            "estudiantes/detalle.html",
            contexto,
            {PANEL: "estudiantes/_detalle.html"},
        )

    def get(self, request, pk):
        estudiante = get_object_or_404(Estudiante.objects.select_related("institucion"), pk=pk)
        return self._responder(request, estudiante)

    def post(self, request, pk):
        estudiante = get_object_or_404(Estudiante.objects.select_related("institucion"), pk=pk)
        accion = request.POST.get("accion")
        if accion == "autorizar":
            form = AutorizacionForm(request.POST)
            if form.is_valid():
                datos = {k: v for k, v in form.cleaned_data.items() if k != "confirmo"}
                if operar(request, form, "estudiante.autorizar", {"estudiante": pk, **datos}):
                    messages.success(request, "Autorización registrada.")
                    return self._listo(request, pk)
            return self._responder(request, estudiante, form_autorizar=form)
        form = RevocarForm(request.POST)
        if form.is_valid() and operar(
            request, form, "estudiante.revocar", {"estudiante": pk, **form.cleaned_data}
        ):
            messages.success(request, "Autorización revocada y plantillas faciales borradas.")
            return self._listo(request, pk)
        return self._responder(request, estudiante, form_revocar=form)

    def _listo(self, request, pk):
        if es_htmx(request):
            estudiante = Estudiante.objects.select_related("institucion").get(pk=pk)
            respuesta = self._responder(request, estudiante)
            return disparar(respuesta, "estudiantes-actualizado")
        return redirect("estudiantes:detalle", pk=pk)


class ExportarView(AdministradorRequeridoMixin, View):
    """Lista del día por estudiante en Excel (constancia de la entrega del PAE)."""

    def get(self, request):
        f = _filtros(request)
        if f["institucion"] is None:
            messages.error(request, "No hay estudiantes importados.")
            return redirect("estudiantes:lista")
        qs = consultas.con_estado_del_dia(
            _estudiantes(f["institucion"]).filter(activo=True), f["fecha"]
        )
        if f["grado"]:
            qs = qs.filter(grado=f["grado"])
            if f["grupo"]:
                qs = qs.filter(grupo=f["grupo"])
        libro = Workbook()
        hoja = libro.active
        hoja.title = "Entrega PAE"
        hoja.append([f"{f['institucion']} — entrega del PAE del {f['fecha']:%Y-%m-%d}"])
        hoja.append(["Curso", "Apellidos", "Nombres", "Documento", "Recibió", "Método", "Hora"])
        for e in qs:
            entrega = e.entregas_del_dia[0] if e.entregas_del_dia else None
            hoja.append(
                [
                    e.curso,
                    e.apellidos,
                    e.nombres,
                    f"{e.tipo_documento} {e.numero_documento}",
                    "Sí" if entrega else "No",
                    entrega.get_metodo_display() if entrega else "",
                    timezone.localtime(entrega.ocurrido_en).strftime("%H:%M") if entrega else "",
                ]
            )
        registrar(
            request.user,
            Accion.EXPORTAR_REPORTE,
            f"Entrega PAE por estudiante ({f['institucion']}, {f['fecha']:%Y-%m-%d})",
            request=request,
            datos={"formato": "xlsx", "institucion": f["institucion"].pk},
        )
        respuesta = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        respuesta["Content-Disposition"] = (
            f'attachment; filename="entrega-pae-{f["fecha"]:%Y-%m-%d}.xlsx"'
        )
        libro.save(respuesta)
        return respuesta
