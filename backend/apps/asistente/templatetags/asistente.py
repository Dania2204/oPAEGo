"""Markdown mínimo y seguro para las respuestas del asistente.

Primero se escapa todo el HTML; luego se reconocen solo párrafos, listas,
tablas simples, **negrita**, `código` y enlaces internos del panel ([texto](/ruta)).
Un enlace a otro sitio se muestra como texto: la respuesta no puede llevar al
administrador fuera de PAEGo.
"""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_NEGRITA = re.compile(r"\*\*(.+?)\*\*")
_CODIGO = re.compile(r"`([^`]+)`")
_ENLACE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_VINETA = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMERO = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_SEPARADOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _enlace(m):
    texto, ruta = m.group(1), m.group(2)
    # Solo rutas del propio panel ("/reportes/?..."), nunca "//sitio" ni "http...".
    if ruta.startswith("/") and not ruta.startswith("//"):
        return f'<a href="{ruta}">{texto}</a>'
    return texto


def _linea(texto):
    texto = escape(texto)
    texto = _CODIGO.sub(r"<code>\1</code>", texto)
    texto = _NEGRITA.sub(r"<strong>\1</strong>", texto)
    # escape() ya convirtió & en &amp; dentro de la ruta: el enlace sigue siendo válido.
    return _ENLACE.sub(_enlace, texto)


def _celdas(fila):
    fila = fila.strip()
    if fila.startswith("|"):
        fila = fila[1:]
    if fila.endswith("|"):
        fila = fila[:-1]
    return [c.strip() for c in fila.split("|")]


def _tabla(filas):
    cabecera, *cuerpo = filas
    html = ['<div class="tabla-scroll"><table><thead><tr>']
    html += [f"<th>{_linea(c)}</th>" for c in _celdas(cabecera)]
    html.append("</tr></thead><tbody>")
    for fila in cuerpo:
        if _SEPARADOR.match(fila):
            continue
        html.append("<tr>" + "".join(f"<td>{_linea(c)}</td>" for c in _celdas(fila)) + "</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


@register.filter
def md_seguro(texto):
    lineas = (texto or "").replace("\r\n", "\n").split("\n")
    bloques = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if not linea.strip():
            i += 1
            continue
        if linea.lstrip().startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].lstrip().startswith("|"):
                filas.append(lineas[i])
                i += 1
            bloques.append(_tabla(filas))
            continue
        for patron, etiqueta in ((_VINETA, "ul"), (_NUMERO, "ol")):
            if patron.match(linea):
                items = []
                while i < len(lineas) and patron.match(lineas[i]):
                    items.append(f"<li>{_linea(patron.match(lineas[i]).group(1))}</li>")
                    i += 1
                bloques.append(f"<{etiqueta}>{''.join(items)}</{etiqueta}>")
                break
        else:
            parrafo = []
            while (
                i < len(lineas)
                and lineas[i].strip()
                and not lineas[i].lstrip().startswith("|")
                and not _VINETA.match(lineas[i])
                and not _NUMERO.match(lineas[i])
            ):
                parrafo.append(_linea(lineas[i].strip().lstrip("#").strip()))
                i += 1
            bloques.append(f"<p>{'<br>'.join(parrafo)}</p>")
    return mark_safe("".join(bloques))
