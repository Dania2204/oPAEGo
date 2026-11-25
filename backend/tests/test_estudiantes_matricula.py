"""Matrícula desde el panel: actualizar con el Anexo 6A y agregar estudiantes a mano."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.catalogo.simat import AnexoInvalido
from apps.estudiantes import importacion, servicios
from apps.estudiantes.models import (
    PREFIJO_MANUAL,
    EstadoImportacion,
    Estudiante,
    ImportacionEstudiantes,
)

from .test_importar_estudiantes import _fila, _xlsx

DANE = "152001000661"


def _subir(web_admin, institucion, ruta, dane=DANE):
    with open(ruta, "rb") as f:
        archivo = SimpleUploadedFile("anexo.xlsx", f.read())
    return web_admin.post(
        f"{reverse('estudiantes:importar')}?institucion={institucion.pk}",
        {"archivo": archivo, "codigo_dane": dane},
    )


# Año 1: Ana y Luis en 7°, Sara en 11°. Año 2: Sara se graduó, Ana y Luis pasan a 8°,
# llega Eva a transición; Pedro está en preescolar (no es población del PAE).
ANO_1 = [
    _fila(DANE, 9001, 1085000001.0, "ROSERO", "ANA", "7", "701"),
    _fila(DANE, 9002, 1085000002.0, "DÍAZ", "LUIS", "7", "701"),
    _fila(DANE, 9003, 1085000003.0, "MORA", "SARA", "11", "1101"),
    _fila("152001999999", 9100, 1085000100.0, "OTRO", "COLEGIO", "5", "501"),
]
ANO_2 = [
    _fila(DANE, 9001, 1085000001.0, "ROSERO", "ANA", "8", "801"),
    _fila(DANE, 9002, 1085000002.0, "DÍAZ", "LUIS", "8", "802"),
    _fila(DANE, 9004, 1085000004.0, "PAZ", "EVA", "0", "01"),
    _fila(DANE, 9005, 1085000005.0, "RUIZ", "PEDRO", "-1", "J1"),
]


# ------------------------------------------------------------------ lectura
def test_leer_filtra_institucion_y_grados_del_pae(tmp_path):
    leidos = importacion.leer(_xlsx(tmp_path, ANO_1 + ANO_2[3:]), [DANE])
    assert set(leidos) == {"9001", "9002", "9003"}  # sin otro colegio ni preescolar
    assert leidos["9001"]["nombres"] == "Ana"


def test_leer_sin_estudiantes_del_dane(tmp_path):
    with pytest.raises(AnexoInvalido, match="No hay estudiantes con el código DANE 999"):
        importacion.leer(_xlsx(tmp_path, ANO_1), ["999"])


# ------------------------------------------------------- flujo en el panel
def test_cambio_de_ano_con_vista_previa(web_admin, admin, institucion, tmp_path):
    importacion.aplicar(institucion, importacion.leer(_xlsx(tmp_path, ANO_1), [DANE]))
    qr_ana = Estudiante.objects.get(simat_per_id="9001").codigo_qr

    r = web_admin.get(reverse("estudiantes:importar"), {"institucion": institucion.pk})
    assert r.status_code == 200 and "Anexo 6A" in r.content.decode()

    r = _subir(web_admin, institucion, _xlsx(tmp_path, ANO_2, "ano2.xlsx"))
    imp = ImportacionEstudiantes.objects.get()
    assert r.status_code == 302 and r["Location"] == reverse(
        "estudiantes:importacion", args=[imp.pk]
    )
    # Paso 1: solo se muestra qué cambiaría; la matrícula sigue igual.
    assert imp.estado == EstadoImportacion.PENDIENTE
    assert (imp.resumen["nuevos"], imp.resumen["cambian_curso"], imp.resumen["bajas"]) == (1, 2, 1)
    assert Estudiante.objects.get(simat_per_id="9003").activo
    html = web_admin.get(r["Location"]).content.decode()
    assert "Revise los cambios" in html and "7° 701" in html and "8° 801" in html
    assert "11° 1101" in html  # sale de la matrícula
    # La lista de la institución avisa que hay una actualización sin confirmar.
    lista = web_admin.get(reverse("estudiantes:lista"), {"institucion": institucion.pk})
    assert "sin confirmar" in lista.content.decode()

    # Paso 2: aplicar.
    r = web_admin.post(r["Location"], {"accion": "aplicar"})
    assert r.status_code == 302
    ana = Estudiante.objects.get(simat_per_id="9001")
    assert (ana.grado, ana.grupo, ana.codigo_qr) == ("8", "801", qr_ana)
    assert not Estudiante.objects.get(simat_per_id="9003").activo
    assert Estudiante.objects.filter(simat_per_id="9004", grado="0").exists()
    assert not Estudiante.objects.filter(simat_per_id="9005").exists()
    imp.refresh_from_db()
    institucion.refresh_from_db()
    assert imp.estado == EstadoImportacion.APLICADA and imp.filas == {}  # no queda copia
    assert institucion.codigo_dane == DANE
    registro = RegistroAuditoria.objects.get(accion=Accion.MATRICULA_ACTUALIZADA, usuario=admin)
    assert registro.usuario == admin and registro.datos["bajas"] == 1

    # Aplicarla otra vez no hace nada.
    r = web_admin.post(reverse("estudiantes:importacion", args=[imp.pk]), {"accion": "aplicar"})
    assert RegistroAuditoria.objects.filter(accion=Accion.MATRICULA_ACTUALIZADA).count() == 2


def test_descartar_no_cambia_nada(web_admin, institucion, tmp_path):
    _subir(web_admin, institucion, _xlsx(tmp_path, ANO_1))
    imp = ImportacionEstudiantes.objects.get()
    web_admin.post(reverse("estudiantes:importacion", args=[imp.pk]), {"accion": "descartar"})
    imp.refresh_from_db()
    assert imp.estado == EstadoImportacion.DESCARTADA and imp.filas == {}
    assert not Estudiante.objects.exists()


def test_nueva_subida_reemplaza_la_pendiente(web_admin, institucion, tmp_path):
    _subir(web_admin, institucion, _xlsx(tmp_path, ANO_1))
    _subir(web_admin, institucion, _xlsx(tmp_path, ANO_2, "b.xlsx"))
    estados = list(ImportacionEstudiantes.objects.order_by("pk").values_list("estado", flat=True))
    assert estados == [EstadoImportacion.DESCARTADA, EstadoImportacion.PENDIENTE]


def test_archivo_invalido_o_dane_equivocado(web_admin, institucion, tmp_path):
    url = f"{reverse('estudiantes:importar')}?institucion={institucion.pk}"
    r = web_admin.post(
        url, {"archivo": SimpleUploadedFile("lista.csv", b"a,b"), "codigo_dane": DANE}
    )
    assert "formato Excel" in r.content.decode()
    r = web_admin.post(
        url, {"archivo": SimpleUploadedFile("roto.xlsx", b"no es excel"), "codigo_dane": DANE}
    )
    assert "No se pudo leer el archivo" in r.content.decode()
    r = _subir(web_admin, institucion, _xlsx(tmp_path, ANO_1), dane="152001000000")
    assert "No hay estudiantes con el código DANE" in r.content.decode()
    assert not ImportacionEstudiantes.objects.exists()


# ------------------------------------------------- estudiante a mitad de año
DATOS = {
    "tipo_documento": "2",
    "numero_documento": "1085000077",
    "nombres": "  juan   josé ",
    "apellidos": "ortiz",
    "grado": "7",
    "grupo": "701",
    "jornada": "1",
}


def test_agregar_estudiante_a_su_curso(web_admin, admin, institucion):
    url = f"{reverse('estudiantes:nuevo')}?institucion={institucion.pk}"
    r = web_admin.get(
        url + "&grado=7&grupo=701", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="panel-contenido"
    )
    html = r.content.decode()
    assert "Agregar estudiante" in html and 'value="701"' in html and "<html" not in html

    r = web_admin.post(url, DATOS, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="panel-contenido")
    assert r.status_code == 200
    assert "estudiantes-actualizado" in r["HX-Trigger"]
    juan = Estudiante.objects.get(numero_documento="1085000077")
    assert (juan.nombres, juan.apellidos, juan.curso) == ("Juan José", "Ortiz", "7° 701")
    assert juan.simat_per_id.startswith(PREFIJO_MANUAL) and juan.activo and juan.codigo_qr
    assert "Imprimir carné" in r.content.decode()  # queda en su ficha, con el QR
    assert RegistroAuditoria.objects.filter(
        accion=Accion.ESTUDIANTE_AGREGADO, usuario=admin
    ).exists()

    # El mismo documento no se agrega dos veces.
    r = web_admin.post(url, DATOS)
    assert "Ya está en la matrícula" in r.content.decode()
    assert Estudiante.objects.filter(numero_documento="1085000077").count() == 1


def test_agregar_sin_htmx_vuelve_al_curso(web_admin, institucion):
    r = web_admin.post(f"{reverse('estudiantes:nuevo')}?institucion={institucion.pk}", DATOS)
    assert r.status_code == 302 and "grado=7" in r["Location"] and "grupo=701" in r["Location"]


def test_simat_reconoce_al_agregado_a_mano(admin, institucion, tmp_path):
    juan, _ = servicios.agregar_estudiante(admin, institucion, DATOS)
    qr = juan.codigo_qr
    filas = [_fila(DANE, 9010, 1085000077.0, "ORTIZ", "JUAN", "7", "701"), ANO_1[0]]
    r = importacion.aplicar(institucion, importacion.leer(_xlsx(tmp_path, filas), [DANE]))
    assert r["nuevos"] == 1  # solo Ana; Juan ya estaba
    juan.refresh_from_db()
    assert juan.simat_per_id == "9010" and juan.codigo_qr == qr and juan.activo


def test_agregado_a_mano_que_no_viene_en_simat_se_conserva(admin, institucion, tmp_path):
    juan, _ = servicios.agregar_estudiante(admin, institucion, DATOS)
    r = importacion.aplicar(institucion, importacion.leer(_xlsx(tmp_path, ANO_1), [DANE]))
    assert r["manuales_conservados"] == 1 and r["bajas"] == 0
    juan.refresh_from_db()
    assert juan.activo


def test_retirar_y_volver_a_agregar(web_admin, admin, institucion):
    juan, _ = servicios.agregar_estudiante(admin, institucion, DATOS)
    qr = juan.codigo_qr
    r = web_admin.post(reverse("estudiantes:detalle", args=[juan.pk]), {"accion": "retirar"})
    assert r.status_code == 302
    juan.refresh_from_db()
    assert not juan.activo and juan.codigo_qr == qr
    assert RegistroAuditoria.objects.filter(accion=Accion.DESACTIVAR).exists()

    # Vuelve a la institución en otro curso: mismo registro, mismo QR.
    vuelve, reactivado = servicios.agregar_estudiante(
        admin, institucion, {**DATOS, "grado": "8", "grupo": "801"}
    )
    assert reactivado and vuelve.pk == juan.pk and vuelve.activo and vuelve.curso == "8° 801"


def test_solo_el_administrador_agrega(supervisor, institucion):
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        servicios.agregar_estudiante(supervisor, institucion, DATOS)
