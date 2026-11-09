"""Importación de la matrícula de SIMAT como conteos agregados (sin PII)."""

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.catalogo.models import Institucion, MatriculaSede

# Cabecera con columnas de identidad (PII) a propósito, para comprobar que el
# comando las ignora por completo.
CABECERA = [
    "ANO_INF",
    "CODIGO_DANE",
    "CONS_SEDE",
    "GRADO",
    "TIPO_JORNADA",
    "ZONA",
    "NOMBRE1",
    "NRO_DOCUMENTO",
]

# (DANE, CONS_SEDE, GRADO, JORNADA, ZONA, NOMBRE, DOCUMENTO)
FILAS = [
    ("100", "10001", "5", "1", "URBANA", "ANA", "111"),
    ("100", "10001", "5", "1", "URBANA", "LUIS", "222"),
    ("100", "10001", "5", "1", "URBANA", "SARA", "333"),
    ("100", "10001", "6", "1", "URBANA", "JOSE", "444"),
    ("100", "10001", "6", "1", "URBANA", "EVA", "555"),
    ("100", "10002", "0", "2", "RURAL", "NIDIA", "666"),
    ("100", "10002", "0", "2", "RURAL", "OMAR", "777"),
    ("100", "10002", "0", "2", "RURAL", "RITA", "888"),
    ("100", "10002", "0", "2", "RURAL", "TITO", "999"),
    ("200", "20001", "5", "1", "URBANA", "OTRO", "000"),  # otra institución (otro DANE)
]

NOMBRES_PII = {f[5] for f in FILAS} | {f[6] for f in FILAS}


def _xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(CABECERA)
    for f in FILAS:
        ws.append([2026, f[0], f[1], f[2], f[3], f[4], f[5], f[6]])
    ruta = tmp_path / "anexo6a.xlsx"
    wb.save(ruta)
    return str(ruta)


def _csv(tmp_path, incluir_10002=True):
    lineas = [
        "consecutivo_sede,nombre,sede,direccion,latitud,longitud",
        "10001,Normal Superior,Sede A,Calle 1,1.210000,-77.280000",
    ]
    if incluir_10002:
        lineas.append("10002,Normal Superior,Sede B,Vereda X,1.190000,-77.300000")
    ruta = tmp_path / "sedes.csv"
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return str(ruta)


@pytest.fixture
def archivos(tmp_path):
    return _xlsx(tmp_path), _csv(tmp_path)


def test_importa_conteos_por_sede(db, archivos):
    xlsx, csv = archivos
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)

    sede_a = Institucion.objects.get(consecutivo_sede="10001")
    sede_b = Institucion.objects.get(consecutivo_sede="10002")
    assert sede_a.codigo_dane == "100"
    assert sede_a.beneficiarios_total == 5  # 3 (5°) + 2 (6°)
    assert sede_b.beneficiarios_total == 4

    # El desglose por grado/jornada queda como filas agregadas, no por estudiante.
    assert MatriculaSede.objects.filter(institucion=sede_a).count() == 2
    assert MatriculaSede.objects.get(institucion=sede_a, grado="5").total == 3
    assert MatriculaSede.objects.get(institucion=sede_b, grado="0", zona="RURAL").total == 4


def test_filtra_por_dane(db, archivos):
    xlsx, csv = archivos
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    # La sede del DANE 200 no debe importarse.
    assert not Institucion.objects.filter(consecutivo_sede="20001").exists()
    assert Institucion.objects.filter(codigo_dane="100").count() == 2


def test_no_almacena_datos_personales(db, archivos):
    xlsx, csv = archivos
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    # Ningún nombre ni documento de estudiante debe aparecer en la base.
    nombres_inst = set(Institucion.objects.values_list("nombre", flat=True)) | set(
        Institucion.objects.values_list("sede", flat=True)
    )
    assert nombres_inst.isdisjoint(NOMBRES_PII)
    # Los totales suman exactamente el número de estudiantes del DANE 100 (9).
    assert sum(MatriculaSede.objects.values_list("total", flat=True)) == 9


def test_es_idempotente(db, archivos):
    xlsx, csv = archivos
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    assert Institucion.objects.filter(codigo_dane="100").count() == 2
    assert MatriculaSede.objects.count() == 3  # 2 de la sede A + 1 de la sede B
    assert Institucion.objects.get(consecutivo_sede="10001").beneficiarios_total == 5


def test_omite_sede_sin_coordenadas(db, tmp_path):
    xlsx = _xlsx(tmp_path)
    csv = _csv(tmp_path, incluir_10002=False)  # falta la 10002
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    assert Institucion.objects.filter(consecutivo_sede="10001").exists()
    assert not Institucion.objects.filter(consecutivo_sede="10002").exists()


def test_dry_run_no_escribe(db, archivos):
    xlsx, csv = archivos
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv, "--dry-run")
    assert Institucion.objects.count() == 0
    assert MatriculaSede.objects.count() == 0


def test_dane_inexistente_falla(db, archivos):
    xlsx, csv = archivos
    with pytest.raises(CommandError):
        call_command("importar_simat", xlsx, "--dane", "999", "--sedes", csv)


def test_vista_cobertura_muestra_totales(web_admin, archivos):
    xlsx, csv = archivos
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    r = web_admin.get(reverse("monitoreo:cobertura"))
    assert r.status_code == 200
    assert b"Normal Superior" in r.content
    assert b"Ley 1581" in r.content  # la nota de minimización de datos


def test_formulario_envio_sugiere_raciones(web_admin, archivos):
    xlsx, csv = archivos
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    r = web_admin.get(reverse("envios:nuevo"))
    assert r.status_code == 200
    # El editor de alimentos recibe el mapa institución→beneficiarios.
    assert b"data-raciones" in r.content
    sede = Institucion.objects.get(consecutivo_sede="10001")
    assert f'"{sede.pk}": 5'.encode() in r.content


def test_reconcilia_con_sede_existente(db, archivos):
    """Una institución creada a mano (sin consecutivo) se enlaza por nombre+sede."""
    xlsx, csv = archivos
    previa = Institucion.objects.create(
        nombre="Normal Superior",
        sede="Sede A",
        direccion="Calle 1",
        latitud="1.210000",
        longitud="-77.280000",
    )
    call_command("importar_simat", xlsx, "--dane", "100", "--sedes", csv)
    previa.refresh_from_db()
    assert previa.consecutivo_sede == "10001"
    assert previa.beneficiarios_total == 5
    # No se duplicó la sede A.
    assert Institucion.objects.filter(nombre="Normal Superior", sede="Sede A").count() == 1
