"""Panel web del administrador: entrega del PAE por estudiante.

El supervisor trabaja en la app móvil y registra la entrega escaneando el código QR
del estudiante. Aquí el administrador ve la cobertura del día por curso y por
estudiante, consulta la ficha con su QR, imprime los carnés de un curso, regenera
un código perdido y exporta la lista del día.
"""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views import View
from openpyxl import Workbook

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.catalogo.models import Institucion
from apps.catalogo.simat import etiqueta_grado, etiqueta_jornada
from apps.comun import PANEL, disparar, es_htmx, responder
from apps.cuentas.permisos import AdministradorRequeridoMixin

from . import consultas, qr, servicios
from .models import Estudiante


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
    def _responder(self, request, estudiante):
        contexto = {
            "estudiante": estudiante,
            "jornada": etiqueta_jornada(estudiante.jornada) if estudiante.jornada else "",
            "qr_svg": mark_safe(qr.svg(estudiante)),  # noqa: S308 — SVG generado aquí, sin datos del usuario
            "entregas": estudiante.entregas.select_related("supervisor")[:30],
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
        """Regenera el código QR (carné perdido): el anterior deja de servir."""
        estudiante = get_object_or_404(Estudiante.objects.select_related("institucion"), pk=pk)
        servicios.regenerar_qr(request.user, estudiante, request=request)
        messages.success(request, "Código QR regenerado. Imprima el carné nuevo.")
        if es_htmx(request):
            return disparar(self._responder(request, estudiante), "estudiantes-actualizado")
        return redirect("estudiantes:detalle", pk=pk)


class CarnesView(AdministradorRequeridoMixin, View):
    """PDF con los carnés QR de un curso (o de un estudiante con `?estudiante=`)."""

    def get(self, request):
        f = _filtros(request)
        if f["institucion"] is None:
            messages.error(request, "No hay estudiantes importados.")
            return redirect("estudiantes:lista")
        qs = _estudiantes(f["institucion"]).filter(activo=True).select_related("institucion")
        if request.GET.get("estudiante"):
            qs = qs.filter(pk=request.GET["estudiante"])
            nombre = "carne-pae"
        elif f["grado"]:
            qs = consultas.estudiantes_del_curso(qs, f["grado"], f["grupo"])
            nombre = f"carnes-pae-{etiqueta_grado(f['grado'])}-{f['grupo']}".replace("°", "")
        else:
            messages.error(request, "Elija un curso para imprimir sus carnés.")
            return redirect("estudiantes:lista")
        qs = qs.order_by("apellidos", "nombres")
        registrar(
            request.user,
            Accion.EXPORTAR_REPORTE,
            f"Carnés QR del PAE ({f['institucion']}, {qs.count()} estudiantes)",
            request=request,
            datos={"formato": "pdf", "institucion": f["institucion"].pk},
        )
        respuesta = HttpResponse(qr.carnes_pdf(qs), content_type="application/pdf")
        respuesta["Content-Disposition"] = f'inline; filename="{slugify(nombre)}.pdf"'
        return respuesta


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
                    e.documento,
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
