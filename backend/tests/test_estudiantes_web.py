"""Panel web: supervisores PAE (catálogo) y la página Estudiantes PAE."""

import io
import uuid

import openpyxl
import pytest
from django.urls import reverse

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.cuentas.models import Rol, Usuario
from apps.estudiantes import servicios
from apps.estudiantes.models import AutorizacionBiometrica, PlantillaFacial, Supervisor

from .test_estudiantes import ACUDIENTE, MUESTRAS, _estudiante


@pytest.fixture
def curso(institucion):
    return [_estudiante(institucion, per_id=f"P{i}", apellidos=f"Apellido{i}") for i in range(3)]


# ------------------------------------------------------------- supervisores
def test_admin_crea_un_supervisor(web_admin, institucion):
    r = web_admin.post(
        reverse("catalogo:nuevo", args=["supervisores"]),
        {
            "first_name": "Sofía",
            "last_name": "Supervisora",
            "email": "sofia@paego.local",
            "password": "Clave-Segura-2026",
            "institucion": institucion.pk,
            "uuid_cliente": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 302
    usuario = Usuario.objects.get(email="sofia@paego.local")
    assert usuario.rol == Rol.SUPERVISOR
    assert Supervisor.objects.get(usuario=usuario).institucion == institucion


def test_lista_y_desactivar_supervisor(web_admin, supervisor):
    r = web_admin.get(reverse("catalogo:lista", args=["supervisores"]))
    assert r.status_code == 200
    assert "Supervisora" in r.content.decode()
    perfil = Supervisor.objects.get(usuario=supervisor)
    web_admin.post(reverse("catalogo:estado", args=["supervisores", perfil.pk]))
    supervisor.refresh_from_db()
    perfil.refresh_from_db()
    assert not perfil.activo and not supervisor.is_active


# ------------------------------------------------------- Estudiantes PAE
def test_pagina_sin_estudiantes(web_admin):
    r = web_admin.get(reverse("estudiantes:lista"))
    assert r.status_code == 200
    assert "importar_estudiantes" in r.content.decode()


def test_cobertura_y_lista_del_curso(web_admin, supervisor, curso):
    servicios.registrar_entrega(supervisor, curso[0], metodo="MANUAL", motivo="Sin cámara")
    r = web_admin.get(reverse("estudiantes:lista"))
    html = r.content.decode()
    assert "7° B" in html and "Recibieron el PAE" in html
    assert r.context["cobertura"]["recibieron"] == 1

    r = web_admin.get(reverse("estudiantes:lista"), {"grado": "7", "grupo": "B"})
    html = r.content.decode()
    assert "Apellido0" in html and "Recibió" in html and "Pendiente" in html


def test_detalle_autorizar_y_revocar(web_admin, supervisor, curso):
    est = curso[0]
    url = reverse("estudiantes:detalle", args=[est.pk])
    assert web_admin.get(url).status_code == 200

    # Sin la confirmación del documento firmado no se registra.
    r = web_admin.post(url, {"accion": "autorizar", **ACUDIENTE, "uuid_cliente": str(uuid.uuid4())})
    assert r.status_code == 200
    assert not AutorizacionBiometrica.objects.exists()

    r = web_admin.post(
        url,
        {"accion": "autorizar", **ACUDIENTE, "confirmo": "on", "uuid_cliente": str(uuid.uuid4())},
    )
    assert r.status_code == 302
    est.refresh_from_db()
    assert est.autorizacion_vigente is not None

    servicios.inscribir_rostro(supervisor, est, vectores=MUESTRAS, modelo="m")
    r = web_admin.post(
        url, {"accion": "revocar", "motivo": "Lo pidió el padre", "uuid_cliente": str(uuid.uuid4())}
    )
    assert r.status_code == 302
    assert not PlantillaFacial.objects.exists()


def test_detalle_por_htmx_en_el_panel(web_admin, curso):
    url = reverse("estudiantes:detalle", args=[curso[0].pk])
    r = web_admin.get(url, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="panel-contenido")
    html = r.content.decode()
    assert "panel-cabeza" in html and "<html" not in html
    r = web_admin.post(
        url,
        {"accion": "autorizar", **ACUDIENTE, "confirmo": "on", "uuid_cliente": str(uuid.uuid4())},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="panel-contenido",
    )
    assert r.status_code == 200
    assert "estudiantes-actualizado" in r["HX-Trigger"]


def test_exportar_excel(web_admin, supervisor, curso):
    servicios.autorizar(supervisor, curso[1], **ACUDIENTE)
    servicios.registrar_entrega(supervisor, curso[0], metodo="MANUAL", motivo="x")
    r = web_admin.get(reverse("estudiantes:exportar"))
    assert r.status_code == 200
    hoja = openpyxl.load_workbook(io.BytesIO(r.content)).active
    filas = list(hoja.iter_rows(min_row=3, values_only=True))
    assert len(filas) == 3
    assert sum(1 for f in filas if f[4] == "Sí") == 1
    assert RegistroAuditoria.objects.filter(accion=Accion.EXPORTAR_REPORTE).exists()


def test_exportar_sin_estudiantes_redirige(web_admin):
    r = web_admin.get(reverse("estudiantes:exportar"))
    assert r.status_code == 302


def test_supervisor_no_entra_a_la_web(client, supervisor, curso):
    from apps.cuentas.tokens import emitir_tokens, poner_cookies

    class _R(dict):
        def set_cookie(self, clave, valor, **kwargs):
            self[clave] = valor

    cookies = _R()
    poner_cookies(cookies, emitir_tokens(supervisor))
    for clave, valor in cookies.items():
        client.cookies[clave] = valor
    assert client.get(reverse("estudiantes:lista")).status_code == 403
