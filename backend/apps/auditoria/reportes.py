"""RF-36 / RF-37: reportes por periodo, institución y conductor, exportables
a PDF y Excel."""

from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.monitoreo import kpis

COLUMNAS = [
    ("codigo", "Código"),
    ("programado", "Programado"),
    ("institucion", "Institución"),
    ("conductor", "Conductor"),
    ("vehiculo", "Vehículo"),
    ("estado", "Estado"),
    ("salida", "Salida"),
    ("llegada", "Llegada"),
    ("entrega", "Entrega"),
    ("a_tiempo", "A tiempo"),
    ("registro_completo", "Registro completo"),
    ("evidencia", "Evidencia verificable"),
    ("novedades", "Novedades"),
]


def _fecha(valor):
    return timezone.localtime(valor).strftime("%Y-%m-%d %H:%M") if valor else ""


def _si_no(valor):
    if valor is None:
        return "—"
    return "Sí" if valor else "No"


def construir(desde=None, hasta=None, institucion=None, conductor=None):
    envios = kpis.envios_del_periodo(desde, hasta, institucion, conductor).order_by(
        "programado_para"
    )
    filas = []
    for e in envios:
        evidencia = getattr(e, "evidencia", None)
        filas.append(
            {
                "codigo": e.codigo,
                "programado": _fecha(e.programado_para),
                "institucion": str(e.institucion),
                "conductor": e.conductor.usuario.get_full_name(),
                "vehiculo": e.vehiculo.placa if e.vehiculo else "",
                "estado": e.get_estado_display(),
                "salida": _fecha(e.salida_en),
                "llegada": _fecha(e.llegada_en),
                "entrega": _fecha(e.entregado_en),
                "a_tiempo": _si_no(e.entregado_a_tiempo),
                "registro_completo": _si_no(e.tiene_registro_completo if e.fue_entregado else None),
                "evidencia": _si_no(evidencia.es_integra if evidencia else None),
                "novedades": e.novedades.count(),
            }
        )
    return {
        "filtros": {
            "desde": desde.isoformat() if desde else None,
            "hasta": hasta.isoformat() if hasta else None,
            "institucion": str(institucion) if institucion else None,
            "conductor": str(conductor) if conductor else None,
        },
        "indicadores": kpis.calcular(desde, hasta, institucion, conductor).como_dict(),
        "columnas": COLUMNAS,
        "filas": filas,
        "generado_en": _fecha(timezone.now()),
    }


def _descripcion_filtros(reporte):
    f = reporte["filtros"]
    partes = [
        f"Desde: {f['desde'] or 'inicio'}",
        f"Hasta: {f['hasta'] or 'hoy'}",
        f"Institución: {f['institucion'] or 'todas'}",
        f"Conductor: {f['conductor'] or 'todos'}",
    ]
    return " · ".join(partes)


def _lineas_indicadores(reporte):
    i = reporte["indicadores"]

    def pct(valor):
        return "—" if valor is None else f"{valor} %"

    return [
        ("Total de envíos", i["total_envios"]),
        ("Total de entregas", i["total_entregas"]),
        ("Entregas con registro completo", pct(i["porcentaje_registro_completo"])),
        ("Entregas a tiempo", pct(i["porcentaje_a_tiempo"])),
        ("Novedades registradas", i["novedades"]),
        ("Entregas con evidencia verificable", pct(i["porcentaje_con_evidencia"])),
    ]


def a_excel(reporte):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Envíos"
    hoja.append(["PAEGo — Reporte de entregas del PAE"])
    hoja["A1"].font = Font(bold=True, size=14)
    hoja.append([_descripcion_filtros(reporte)])
    hoja.append([f"Generado: {reporte['generado_en']}"])
    hoja.append([])
    hoja.append([titulo for _, titulo in COLUMNAS])
    encabezado = hoja.max_row
    relleno = PatternFill("solid", fgColor="1D4D20")
    for celda in hoja[encabezado]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = relleno
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for fila in reporte["filas"]:
        hoja.append([fila[clave] for clave, _ in COLUMNAS])
    for indice, (clave, titulo) in enumerate(COLUMNAS, start=1):
        ancho = max([len(titulo)] + [len(str(f[clave])) for f in reporte["filas"]] or [10])
        hoja.column_dimensions[get_column_letter(indice)].width = min(ancho + 2, 45)
    hoja.freeze_panes = hoja.cell(row=encabezado + 1, column=1)

    resumen = libro.create_sheet("Indicadores")
    resumen.append(["Indicador", "Valor"])
    for celda in resumen[1]:
        celda.font = Font(bold=True)
    for nombre, valor in _lineas_indicadores(reporte):
        resumen.append([nombre, valor])
    resumen.append([])
    resumen.append(["Novedades por tipo", ""])
    for tipo, cantidad in reporte["indicadores"]["novedades_por_tipo"].items():
        resumen.append([tipo, cantidad])
    resumen.column_dimensions["A"].width = 40
    resumen.column_dimensions["B"].width = 15

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def a_pdf(reporte):
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida,
        pagesize=landscape(letter),
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Reporte PAEGo",
    )
    estilos = getSampleStyleSheet()
    pequeno = estilos["BodyText"].clone("pequeno", fontSize=7, leading=8.5)
    contenido = [
        Paragraph("PAEGo — Reporte de entregas del PAE", estilos["Title"]),
        Paragraph(_descripcion_filtros(reporte), estilos["Normal"]),
        Paragraph(f"Generado: {reporte['generado_en']}", estilos["Normal"]),
        Spacer(1, 0.4 * cm),
    ]

    tabla_kpi = Table(
        [["Indicador", "Valor"]] + [[n, str(v)] for n, v in _lineas_indicadores(reporte)],
        colWidths=[8 * cm, 4 * cm],
    )
    tabla_kpi.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4d20")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    contenido += [tabla_kpi, Spacer(1, 0.5 * cm)]

    datos = [[Paragraph(f"<b>{t}</b>", pequeno) for _, t in COLUMNAS]]
    for fila in reporte["filas"]:
        datos.append([Paragraph(str(fila[c]), pequeno) for c, _ in COLUMNAS])
    if len(datos) == 1:
        datos.append([Paragraph("Sin envíos en el periodo.", pequeno)] + [""] * (len(COLUMNAS) - 1))
    tabla = Table(datos, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcedd7")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4faf4")]),
            ]
        )
    )
    contenido.append(tabla)
    documento.build(contenido)
    return salida.getvalue()
