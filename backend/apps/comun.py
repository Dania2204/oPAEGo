"""Utilidades compartidas por las vistas web del panel del administrador."""

import json
import uuid

from django.contrib import messages
from django.http import Http404
from django.shortcuts import render
from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from apps.sincronizacion.operaciones import ejecutar

PANEL = "panel-contenido"


def es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def destino_htmx(request):
    """Id del elemento que HTMX va a reemplazar (None si no es HTMX)."""
    return request.headers.get("HX-Target") if es_htmx(request) else None


def responder(request, plantilla, contexto, parciales=None, status=200):
    """Página completa o, si la pide HTMX, solo el fragmento que corresponde
    al elemento destino (`parciales = {"id-destino": "app/_parcial.html"}`)."""
    plantilla_final = (parciales or {}).get(destino_htmx(request), plantilla)
    contexto.setdefault("en_panel", destino_htmx(request) == PANEL)
    respuesta = render(request, plantilla_final, contexto, status=status)
    patch_vary_headers(respuesta, ["HX-Request", "HX-Target"])
    return respuesta


def disparar(respuesta, *eventos, **eventos_con_datos):
    """Agrega eventos HX-Trigger (p. ej. refrescar listas o cerrar el panel)."""
    datos = {e: True for e in eventos}
    datos.update(eventos_con_datos)
    respuesta["HX-Trigger"] = json.dumps(datos)
    return respuesta


def nuevo_uuid():
    """Identificador de la operación: evita duplicados por doble envío del
    formulario y es el mismo que usa la cola sin conexión (RF-38)."""
    return str(uuid.uuid4())


def _textos(valor):
    if isinstance(valor, dict):
        return [t for v in valor.values() for t in _textos(v)]
    if isinstance(valor, (list, tuple)):
        return [t for v in valor for t in _textos(v)]
    return [str(valor)]


def aplicar_errores(form, exc):
    """Traslada los errores de validación de la API al formulario web."""
    detalle = exc.detail if isinstance(exc, APIException) else str(exc)
    if isinstance(detalle, dict):
        for campo, valor in detalle.items():
            destino = campo if campo in form.fields else None
            for texto in _textos(valor):
                form.add_error(destino, texto if destino else f"{campo}: {texto}")
    else:
        for texto in _textos(detalle):
            form.add_error(None, texto)


def operar(request, form, tipo, datos):
    """Ejecuta una operación con las mismas reglas que la API.

    Devuelve la respuesta de la operación o None si hubo errores (que quedan
    cargados en el formulario).
    """
    try:
        _, respuesta = ejecutar(
            request.user,
            tipo,
            datos,
            uuid_cliente=request.POST.get("uuid_cliente") or None,
            request=request,
            propagar=True,
        )
        return respuesta
    except ValidationError as exc:
        aplicar_errores(form, exc)
    except (PermissionDenied, NotFound, Http404) as exc:
        messages.error(request, str(getattr(exc, "detail", exc)))
    return None


def datos_formulario(form):
    """Datos crudos del POST con los nombres de campo de la API."""
    datos = {}
    for nombre in form.fields:
        valor = form.data.get(nombre)
        if valor is None:
            continue
        datos[nombre] = valor
    return datos
