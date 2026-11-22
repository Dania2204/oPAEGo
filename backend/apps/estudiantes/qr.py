"""Código QR del estudiante: SVG para el panel y carnés imprimibles en PDF.

El QR lleva `PAEGO-E1:<codigo_qr>` (ver `Estudiante.contenido_qr`): un token
aleatorio sin datos personales. Se dibuja con el codificador de reportlab, que ya
es dependencia del proyecto (reportes PDF), así que no hace falta otra librería.
"""

from io import BytesIO

from reportlab.graphics.barcode import qrencoder
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.catalogo.simat import etiqueta_jornada

AZUL = HexColor("#004884")
TINTA = HexColor("#1f1f1f")
TENUE = HexColor("#5f6368")
BORDE = HexColor("#c9ced6")


def matriz(texto):
    """Módulos del QR (True = oscuro). Corrección de errores M: tolera manchas leves."""
    codigo = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    codigo.addData(texto)
    codigo.make()
    n = codigo.getModuleCount()
    return [[codigo.isDark(f, c) for c in range(n)] for f in range(n)]


def svg(estudiante, *, margen=4):
    """SVG compacto (un solo trazo) que escala sin perder nitidez."""
    m = matriz(estudiante.contenido_qr)
    n = len(m) + 2 * margen
    trazo = "".join(
        f"M{c + margen} {f + margen}h1v1h-1z"
        for f, fila in enumerate(m)
        for c, oscuro in enumerate(fila)
        if oscuro
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
        f'shape-rendering="crispEdges" role="img" '
        f'aria-label="Código QR de {estudiante.nombre_completo}">'
        f'<rect width="{n}" height="{n}" fill="#fff"/>'
        f'<path d="{trazo}" fill="#000"/></svg>'
    )


def documento_parcial(estudiante):
    """En el carné impreso solo se ven los últimos 4 dígitos (minimización)."""
    numero = estudiante.numero_documento or ""
    visible = numero[-4:]
    return f"{estudiante.tipo_documento_etiqueta} ···{visible}" if visible else ""


# ---------------------------------------------------------------- carnés PDF
ANCHO_CARNE = 9.2 * cm
ALTO_CARNE = 5.8 * cm
COLUMNAS = 2
FILAS = 4
MARGEN_X = (letter[0] - COLUMNAS * ANCHO_CARNE) / 3
MARGEN_Y = (letter[1] - FILAS * ALTO_CARNE) / 5


def _recortar(c, texto, fuente, tamano, ancho):
    """Corta el texto con «…» para que quepa en `ancho`."""
    if c.stringWidth(texto, fuente, tamano) <= ancho:
        return texto
    while texto and c.stringWidth(texto + "…", fuente, tamano) > ancho:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def _dibujar_qr(c, texto, x, y, lado):
    m = matriz(texto)
    modulo = lado / len(m)
    # Un solo trazo con los tramos oscuros de cada fila unidos: si cada módulo fuera
    # un rectángulo suelto, al rasterizar quedan líneas finas entre ellos.
    trazo = c.beginPath()
    for f, fila in enumerate(m):
        col = 0
        while col < len(fila):
            if not fila[col]:
                col += 1
                continue
            inicio = col
            while col < len(fila) and fila[col]:
                col += 1
            # El PDF crece hacia arriba: la fila 0 va arriba.
            trazo.rect(
                x + inicio * modulo,
                y + lado - (f + 1) * modulo,
                (col - inicio) * modulo,
                modulo,
            )
    c.setFillColor(TINTA)
    c.drawPath(trazo, stroke=0, fill=1)


def _carne(c, estudiante, x, y):
    c.setStrokeColor(BORDE)
    c.setLineWidth(0.6)
    c.roundRect(x, y, ANCHO_CARNE, ALTO_CARNE, 6, stroke=1, fill=0)

    # Franja superior con la institución.
    franja = 0.95 * cm
    c.setFillColor(AZUL)
    c.roundRect(x, y + ALTO_CARNE - franja, ANCHO_CARNE, franja, 6, stroke=0, fill=1)
    c.rect(x, y + ALTO_CARNE - franja, ANCHO_CARNE, franja / 2, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 7.5)
    institucion = _recortar(
        c, estudiante.institucion.nombre.upper(), "Helvetica-Bold", 7.5, ANCHO_CARNE - 0.8 * cm
    )
    c.drawString(x + 0.4 * cm, y + ALTO_CARNE - 0.42 * cm, institucion)
    c.setFont("Helvetica", 6.5)
    c.drawString(x + 0.4 * cm, y + ALTO_CARNE - 0.75 * cm, "Programa de Alimentación Escolar · PAE")

    # QR a la derecha.
    lado = 3.9 * cm
    qx = x + ANCHO_CARNE - lado - 0.35 * cm
    qy = y + 0.45 * cm
    _dibujar_qr(c, estudiante.contenido_qr, qx, qy, lado)

    # Datos a la izquierda.
    ancho_texto = qx - x - 0.7 * cm
    tx = x + 0.4 * cm
    ty = y + ALTO_CARNE - franja - 0.75 * cm
    c.setFillColor(TINTA)
    c.setFont("Helvetica-Bold", 10)
    for linea in (estudiante.nombres, estudiante.apellidos):
        c.drawString(tx, ty, _recortar(c, linea, "Helvetica-Bold", 10, ancho_texto))
        ty -= 0.45 * cm
    ty -= 0.25 * cm
    filas = [("Curso", estudiante.curso)]
    if estudiante.jornada:
        filas.append(("Jornada", etiqueta_jornada(estudiante.jornada)))
    documento = documento_parcial(estudiante)
    if documento:
        filas.append(("Documento", documento))
    for etiqueta, valor in filas:
        c.setFont("Helvetica", 6.5)
        c.setFillColor(TENUE)
        c.drawString(tx, ty, etiqueta.upper())
        ty -= 0.34 * cm
        c.setFont("Helvetica", 9)
        c.setFillColor(TINTA)
        c.drawString(tx, ty, _recortar(c, valor, "Helvetica", 9, ancho_texto))
        ty -= 0.48 * cm

    c.setFont("Helvetica", 6)
    c.setFillColor(TENUE)
    c.drawString(tx, y + 0.35 * cm, "Presente este código al recibir el PAE.")


def carnes_pdf(estudiantes, *, titulo="Carnés PAE"):
    """Hoja carta con 8 carnés por página, listos para recortar."""
    salida = BytesIO()
    c = canvas.Canvas(salida, pagesize=letter)
    c.setTitle(titulo)
    c.setAuthor("PAEGo")
    por_pagina = COLUMNAS * FILAS
    estudiantes = list(estudiantes)
    for i, estudiante in enumerate(estudiantes):
        if i and i % por_pagina == 0:
            c.showPage()
        pos = i % por_pagina
        fila, col = divmod(pos, COLUMNAS)
        x = MARGEN_X + col * (ANCHO_CARNE + MARGEN_X)
        y = letter[1] - (fila + 1) * (ALTO_CARNE + MARGEN_Y)
        _carne(c, estudiante, x, y)
    if not estudiantes:
        c.setFont("Helvetica", 11)
        c.drawString(2 * cm, letter[1] - 3 * cm, "No hay estudiantes activos en este curso.")
    c.save()
    return salida.getvalue()
