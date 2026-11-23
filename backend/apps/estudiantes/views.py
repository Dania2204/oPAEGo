"""Panel web del administrador: entrega del PAE por estudiante.

El supervisor trabaja en la app móvil y registra la entrega escaneando el código QR
del estudiante. Aquí el administrador ve la cobertura del día por curso y por
estudiante, consulta la ficha con su QR, imprime los carnés de un curso, regenera
un código perdido y exporta la lista del día. Es multiinstitucional: primero se elige
la institución. La matrícula se mantiene desde aquí: actualizar con el Anexo 6A de
SIMAT (vista previa y confirmación), agregar a quien llega a mitad de año y retirar.
"""

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views import View
from openpyxl import Workbook
from rest_framework.exceptions import ValidationError

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.catalogo.models import Institucion
from apps.catalogo.simat import AnexoInvalido, etiqueta_grado, etiqueta_jornada
from apps.comun import PANEL, aplicar_errores, disparar, es_htmx, responder
from apps.cuentas.permisos import AdministradorRequeridoMixin

from . import consultas, importacion, qr, servicios
from .forms import EstudianteForm, ImportarForm
from .models import EstadoImportacion, Estudiante, ImportacionEstudiantes


def _fecha(request):
    return parse_date(request.GET.get("fecha") or "") or timezone.localdate()


def _instituciones(q=""):
    """Instituciones activas (el sistema es multiinstitucional), con sus estudiantes."""
    qs = Institucion.objects.filter(activo=True).annotate(
        estudiantes_activos=Count("estudiantes", filter=Q(estudiantes__activo=True))
    )
    q = (q or "").strip()
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(sede__icontains=q) | Q(codigo_dane__icontains=q))
    return qs.order_by("nombre", "sede")


def _filtros(request):
    """Institución elegida (None si aún no se elige), fecha y curso."""
    institucion = None
    if (request.GET.get("institucion") or "").isdigit():
        institucion = _instituciones().filter(pk=request.GET["institucion"]).first()
    return {
        "institucion": institucion,
        "fecha": _fecha(request),
        "grado": request.GET.get("grado", ""),
        "grupo": request.GET.get("grupo", ""),
    }


def _url_institucion(institucion, **extra):
    params = "&".join(f"{k}={v}" for k, v in extra.items() if v not in (None, ""))
    url = f"{reverse('estudiantes:lista')}?institucion={institucion.pk}"
    return f"{url}&{params}" if params else url


def _estudiantes(institucion):
    return Estudiante.objects.filter(institucion=institucion)


class EstudiantesView(AdministradorRequeridoMixin, View):
    def get(self, request):
        f = _filtros(request)
        if f["institucion"] is None:
            # Primero se elige la institución (buscador); luego sus estudiantes.
            q = request.GET.get("q", "")
            return responder(
                request,
                "estudiantes/elegir.html",
                {"instituciones": _instituciones(q), "q": q},
                {"instituciones": "estudiantes/_instituciones.html"},
            )
        base = _estudiantes(f["institucion"])
        contexto = {
            **f,
            "hoy": timezone.localdate(),
            "cobertura": consultas.cobertura(base, f["fecha"]),
            "cursos": consultas.resumen_cursos(base, f["fecha"]),
            "pendiente": ImportacionEstudiantes.objects.filter(
                institucion=f["institucion"], estado=EstadoImportacion.PENDIENTE
            ).first(),
        }
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
            {
                "resultados": "estudiantes/_contenido.html",
                # Solo los estudiantes del curso, para abrirlo bajo su fila.
                "curso-detalle": "estudiantes/_curso_detalle.html",
            },
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
        """Regenera el código QR (carné perdido) o retira al estudiante de la matrícula."""
        estudiante = get_object_or_404(Estudiante.objects.select_related("institucion"), pk=pk)
        if request.POST.get("accion") == "retirar":
            servicios.dar_de_baja(estudiante, usuario=request.user, request=request)
            messages.success(
                request, f"{estudiante.nombre_completo} salió de la matrícula; su QR ya no sirve."
            )
        else:
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
            messages.error(request, "Elija primero una institución.")
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
            messages.error(request, "Elija primero una institución.")
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


class EstudianteNuevoView(AdministradorRequeridoMixin, View):
    """Estudiante que llega a mitad de año: queda en su curso con su código QR."""

    def _institucion(self, request):
        return get_object_or_404(
            Institucion.objects.filter(activo=True), pk=request.GET.get("institucion") or 0
        )

    def _responder(self, request, form, institucion, status=200):
        return responder(
            request,
            "estudiantes/nuevo.html",
            {"form": form, "institucion": institucion},
            {PANEL: "estudiantes/_nuevo.html"},
            status=status,
        )

    def get(self, request):
        institucion = self._institucion(request)
        inicial = {"grado": request.GET.get("grado", ""), "grupo": request.GET.get("grupo", "")}
        # El curso ya tiene jornada: se propone la misma.
        jornada = (
            Estudiante.objects.filter(
                institucion=institucion, activo=True, grado=inicial["grado"], grupo=inicial["grupo"]
            )
            .exclude(jornada="")
            .values_list("jornada", flat=True)
            .first()
        )
        if jornada:
            inicial["jornada"] = jornada
        return self._responder(request, EstudianteForm(initial=inicial), institucion)

    def post(self, request):
        institucion = self._institucion(request)
        form = EstudianteForm(request.POST)
        if form.is_valid():
            try:
                estudiante, reactivado = servicios.agregar_estudiante(
                    request.user, institucion, form.cleaned_data, request=request
                )
            except ValidationError as exc:
                aplicar_errores(form, exc)
            else:
                messages.success(
                    request,
                    f"{estudiante.nombre_completo} {'volvió a' if reactivado else 'quedó en'} "
                    f"{estudiante.curso}. Imprima su carné QR.",
                )
                if es_htmx(request):
                    respuesta = EstudianteDetalleView()._responder(request, estudiante)
                    return disparar(respuesta, "estudiantes-actualizado")
                return redirect(
                    _url_institucion(institucion, grado=estudiante.grado, grupo=estudiante.grupo)
                )
        return self._responder(request, form, institucion, status=422 if es_htmx(request) else 200)


class ImportarView(AdministradorRequeridoMixin, View):
    """Paso 1: subir el Anexo 6A. Se lee y se muestra qué va a cambiar."""

    def _institucion(self, request):
        return get_object_or_404(
            Institucion.objects.filter(activo=True), pk=request.GET.get("institucion") or 0
        )

    def _responder(self, request, form, institucion):
        return responder(
            request, "estudiantes/importar.html", {"form": form, "institucion": institucion}
        )

    def get(self, request):
        institucion = self._institucion(request)
        form = ImportarForm(initial={"codigo_dane": institucion.codigo_dane})
        return self._responder(request, form, institucion)

    def post(self, request):
        institucion = self._institucion(request)
        form = ImportarForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._responder(request, form, institucion)
        archivo = form.cleaned_data["archivo"]
        dane = form.cleaned_data["codigo_dane"]
        try:
            leidos = importacion.leer(archivo, [dane])
        except AnexoInvalido as exc:
            form.add_error(None, str(exc))
            return self._responder(request, form, institucion)
        except Exception:  # noqa: BLE001 — archivo dañado o que no es Excel
            form.add_error(
                None, "No se pudo leer el archivo. Verifique que sea el Excel del Anexo 6A."
            )
            return self._responder(request, form, institucion)
        # Una sola importación pendiente por institución: la anterior se descarta.
        for anterior in ImportacionEstudiantes.objects.filter(
            institucion=institucion, estado=EstadoImportacion.PENDIENTE
        ):
            importacion.descartar(anterior)
        nueva = ImportacionEstudiantes.objects.create(
            institucion=institucion,
            usuario=request.user,
            nombre_archivo=archivo.name[:200],
            codigo_dane=dane,
            filas=leidos,
            resumen=importacion.planear(institucion, leidos),
        )
        return redirect("estudiantes:importacion", pk=nueva.pk)


class ImportacionView(AdministradorRequeridoMixin, View):
    """Paso 2: revisar el resumen y aplicar (o descartar) la actualización."""

    def get(self, request, pk):
        imp = get_object_or_404(ImportacionEstudiantes.objects.select_related("institucion"), pk=pk)
        return responder(request, "estudiantes/importacion.html", {"imp": imp, "r": imp.resumen})

    def post(self, request, pk):
        imp = get_object_or_404(ImportacionEstudiantes.objects.select_related("institucion"), pk=pk)
        if imp.estado != EstadoImportacion.PENDIENTE:
            messages.error(request, "Esta actualización ya se aplicó o se descartó.")
            return redirect(_url_institucion(imp.institucion))
        if request.POST.get("accion") == "descartar":
            importacion.descartar(imp)
            messages.success(request, "Actualización descartada; no se cambió nada.")
            return redirect(_url_institucion(imp.institucion))
        r = importacion.confirmar(imp, request.user, request=request)
        messages.success(
            request,
            f"Matrícula actualizada: {r['nuevos']} nuevos, {r['cambian_curso']} cambian de curso, "
            f"{r['bajas']} salen de la matrícula.",
        )
        return redirect(_url_institucion(imp.institucion))
