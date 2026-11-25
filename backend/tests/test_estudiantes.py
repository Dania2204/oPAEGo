"""Entrega del PAE a estudiantes: código QR único, permisos y entrega diaria."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.cuentas.models import Rol
from apps.estudiantes import qr, servicios
from apps.estudiantes.models import (
    PREFIJO_QR,
    EntregaEstudiante,
    EntregaInmutableError,
    Estudiante,
    MetodoEntrega,
)

from .conftest import crear_usuario


def _estudiante(institucion, per_id="P1", **extra):
    datos = {
        "tipo_documento": "TI",
        "numero_documento": f"10{per_id}",
        "nombres": "Ana María",
        "apellidos": "Rosero Díaz",
        "grado": "7",
        "grupo": "B",
        "jornada": "1",
    }
    datos.update(extra)
    return Estudiante.objects.create(institucion=institucion, simat_per_id=per_id, **datos)


@pytest.fixture
def estudiante(institucion):
    return _estudiante(institucion)


# ---------------------------------------------------------------- código QR
def test_cada_estudiante_tiene_un_codigo_unico(institucion):
    a = _estudiante(institucion, per_id="A")
    b = _estudiante(institucion, per_id="B")
    assert len(a.codigo_qr) >= 20
    assert a.codigo_qr != b.codigo_qr
    assert a.contenido_qr == PREFIJO_QR + a.codigo_qr
    # El QR no lleva datos personales.
    assert a.numero_documento not in a.contenido_qr
    assert "Ana" not in a.contenido_qr


def test_codigo_de_acepta_con_y_sin_prefijo():
    assert servicios.codigo_de(" PAEGO-E1:abc ") == "abc"
    assert servicios.codigo_de("abc") == "abc"
    assert servicios.codigo_de(None) == ""


def test_regenerar_qr_invalida_el_anterior(admin, supervisor, estudiante):
    anterior = estudiante.contenido_qr
    nuevo = servicios.regenerar_qr(admin, estudiante)
    assert nuevo != anterior
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="QR", codigo=anterior)
    servicios.registrar_entrega(supervisor, estudiante, metodo="QR", codigo=nuevo)
    assert RegistroAuditoria.objects.filter(accion=Accion.QR_REGENERADO).count() == 1


def test_solo_el_admin_regenera(supervisor, estudiante):
    with pytest.raises(PermissionDenied):
        servicios.regenerar_qr(supervisor, estudiante)


def test_svg_del_qr(estudiante):
    dibujo = qr.svg(estudiante)
    assert dibujo.startswith("<svg") and dibujo.endswith("</svg>")
    assert "Ana María Rosero Díaz" in dibujo  # etiqueta accesible
    # La matriz decodifica a un QR válido (tamaño de versión QR: 21 + 4k).
    assert (len(qr.matriz(estudiante.contenido_qr)) - 21) % 4 == 0


def test_carnes_pdf(institucion):
    estudiantes = [_estudiante(institucion, per_id=f"C{i}") for i in range(9)]
    pdf = qr.carnes_pdf(Estudiante.objects.filter(pk__in=[e.pk for e in estudiantes]))
    assert pdf.startswith(b"%PDF")
    paginas = pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")
    assert paginas == 2  # 8 carnés por hoja
    assert qr.carnes_pdf([]).startswith(b"%PDF")


def test_documento_parcial_en_el_carne(institucion):
    e = _estudiante(institucion, per_id="D1", numero_documento="1085123456")
    assert qr.documento_parcial(e) == "TI ···3456"


def test_dar_de_baja(estudiante):
    servicios.dar_de_baja(estudiante)
    estudiante.refresh_from_db()
    assert not estudiante.activo


# ----------------------------------------------------------------- permisos
def test_supervisor_de_otra_institucion_no_accede(supervisor_otra, estudiante):
    with pytest.raises(PermissionDenied):
        servicios.registrar_entrega(
            supervisor_otra, estudiante, metodo="QR", codigo=estudiante.codigo_qr
        )
    with pytest.raises(PermissionDenied):
        servicios.registrar_entrega(supervisor_otra, estudiante, metodo="MANUAL", motivo="x")


def test_conductor_no_registra_entregas(conductor, estudiante):
    with pytest.raises(PermissionDenied):
        servicios.registrar_entrega(conductor.usuario, estudiante, metodo="MANUAL", motivo="x")


def test_supervisor_sin_institucion_asignada(estudiante):
    u = crear_usuario("suelto@test.co", Rol.SUPERVISOR)
    with pytest.raises(PermissionDenied):
        servicios.estudiantes_visibles(u)


def test_institucion_solo_consulta_lo_suyo(responsable, estudiante, otra_institucion):
    _estudiante(otra_institucion, per_id="P9")
    visibles = servicios.estudiantes_visibles(responsable.usuario, lectura=True)
    assert list(visibles) == [estudiante]
    with pytest.raises(PermissionDenied):
        servicios.estudiantes_visibles(responsable.usuario)


# ------------------------------------------------------------------ entrega
def test_entrega_por_qr(estudiante, supervisor):
    entrega = servicios.registrar_entrega(
        supervisor, estudiante, metodo="QR", codigo=estudiante.contenido_qr
    )
    assert entrega.metodo == MetodoEntrega.QR
    assert entrega.fecha == timezone.localdate()
    assert entrega.get_metodo_display() == "Código QR"
    assert RegistroAuditoria.objects.filter(accion=Accion.ENTREGA_ESTUDIANTE).count() == 1


def test_qr_de_otro_estudiante_se_rechaza(institucion, estudiante, supervisor):
    otro = _estudiante(institucion, per_id="P2")
    with pytest.raises(ValidationError) as error:
        servicios.registrar_entrega(supervisor, estudiante, metodo="QR", codigo=otro.codigo_qr)
    assert error.value.get_codes() == {"codigo": "qr_invalido"}
    assert not EntregaEstudiante.objects.exists()


def test_qr_vacio_se_rechaza(estudiante, supervisor):
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="QR", codigo="PAEGO-E1:")


def test_metodo_facial_ya_no_se_acepta(estudiante, supervisor):
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="FACIAL")


def test_entrega_manual_exige_motivo(supervisor, estudiante):
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="MANUAL", motivo="  ")
    entrega = servicios.registrar_entrega(
        supervisor, estudiante, metodo="MANUAL", motivo="Olvidó el carné"
    )
    assert entrega.motivo == "Olvidó el carné"


def test_una_sola_entrega_por_dia(supervisor, estudiante):
    servicios.registrar_entrega(supervisor, estudiante, metodo="MANUAL", motivo="x")
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="MANUAL", motivo="x")
    # Al día siguiente sí.
    ayer = timezone.now() - timedelta(days=1)
    servicios.registrar_entrega(
        supervisor, estudiante, metodo="MANUAL", motivo="x", ocurrido_en=ayer
    )
    assert EntregaEstudiante.objects.count() == 2


def test_entrega_sin_conexion_queda_diferida(supervisor, estudiante):
    hace_rato = timezone.now() - timedelta(hours=2)
    entrega = servicios.registrar_entrega(
        supervisor, estudiante, metodo="MANUAL", motivo="x", ocurrido_en=hace_rato
    )
    assert entrega.diferido
    assert entrega.ocurrido_en == hace_rato


def test_estudiante_inactivo_no_recibe(supervisor, estudiante):
    servicios.dar_de_baja(estudiante)
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="MANUAL", motivo="x")


def test_entrega_es_inmutable(supervisor, estudiante):
    entrega = servicios.registrar_entrega(supervisor, estudiante, metodo="MANUAL", motivo="x")
    entrega.motivo = "otro"
    with pytest.raises(EntregaInmutableError):
        entrega.save()
    with pytest.raises(EntregaInmutableError):
        entrega.delete()
    with pytest.raises(EntregaInmutableError):
        EntregaEstudiante.objects.all().delete()


def test_curso_legible(estudiante):
    assert estudiante.curso == "7° B"
    assert estudiante.nombre_completo == "Ana María Rosero Díaz"


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [("2", "TI"), ("5", "RC"), ("1", "CC"), ("13", "Doc. 13"), ("TI", "TI"), ("", "")],
)
def test_etiqueta_documento_simat(codigo, esperado):
    from apps.catalogo.simat import etiqueta_documento

    assert etiqueta_documento(codigo) == esperado
