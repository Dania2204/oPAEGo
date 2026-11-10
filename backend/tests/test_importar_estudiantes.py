"""importar_estudiantes: identidad mínima de una institución, sin datos sensibles."""

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.estudiantes import servicios
from apps.estudiantes.models import Estudiante, PlantillaFacial

from .test_estudiantes import ACUDIENTE, MUESTRAS

# Columnas reales del Anexo 6A, incluidas las sensibles (y " NOMBRE1" con espacio,
# como viene en el archivo de SIMAT), para comprobar que no se importan.
CABECERA = [
    "ANO_INF", "CODIGO_DANE", "CONS_SEDE", "PER_ID", "TIPO_DOCUMENTO", "NRO_DOCUMENTO",
    "APELLIDO1", "APELLIDO2", " NOMBRE1", "NOMBRE2", "DIRECCION_RESIDENCIA", "TEL",
    "SISBEN IV", "FECHA_NACIMIENTO", "POB_VICT_CONF_RUV", "TIPO_DISCAPACIDAD", "ETNIA",
    "GRADO", "GRUPO", "TIPO_JORNADA",
]  # fmt: skip

SENSIBLES = ["CALLE 99 # 1-23", "3001234567", "A1", "2014-03-02", "VICTIMA", "VISUAL", "PASTOS"]


def _fila(dane, per_id, doc, ape1, nom1, grado, grupo):
    return [
        2026, dane, "15200100066101", per_id, "TI", doc, ape1, "LÓPEZ", nom1, "", *SENSIBLES,
        grado, grupo, 1,
    ]  # fmt: skip


def _xlsx(tmp_path, filas, nombre="anexo.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(CABECERA)
    for f in filas:
        ws.append(f)
    ruta = tmp_path / nombre
    wb.save(ruta)
    return str(ruta)


FILAS = [
    _fila("152001000661", 9001, 1085000001.0, "ROSERO", "ANA", "7", "B"),
    _fila("152001000661", 9002, 1085000002.0, "DÍAZ", "LUIS", "7", "B"),
    _fila("152001000661", 9003, 1085000003.0, "MORA", "SARA", "11", "A"),
    _fila("152001999999", 9100, 1085000100.0, "OTRO", "COLEGIO", "5", "A"),
]


def _importar(ruta, *extra):
    call_command(
        "importar_estudiantes", ruta, "--dane", "152001000661", "--institucion", "Normal", *extra
    )


def test_importa_solo_la_identidad_minima(institucion, tmp_path):
    _importar(_xlsx(tmp_path, FILAS))
    estudiantes = list(Estudiante.objects.order_by("simat_per_id"))
    assert [e.simat_per_id for e in estudiantes] == ["9001", "9002", "9003"]
    ana = estudiantes[0]
    assert (ana.numero_documento, ana.nombres, ana.apellidos) == (
        "1085000001",
        "Ana",
        "Rosero López",
    )
    assert (ana.grado, ana.grupo, ana.institucion) == ("7", "B", institucion)
    # Ningún dato sensible del Anexo quedó en ningún campo.
    for est in estudiantes:
        valores = " ".join(str(getattr(est, f.attname)) for f in Estudiante._meta.concrete_fields)
        for sensible in SENSIBLES:
            assert sensible not in valores


def test_es_idempotente_y_da_de_baja_a_los_retirados(institucion, tmp_path, supervisor):
    _importar(_xlsx(tmp_path, FILAS))
    _importar(_xlsx(tmp_path, FILAS))
    assert Estudiante.objects.count() == 3

    sara = Estudiante.objects.get(simat_per_id="9003")
    servicios.autorizar(supervisor, sara, **ACUDIENTE)
    servicios.inscribir_rostro(supervisor, sara, vectores=MUESTRAS, modelo="m")

    # Nuevo corte: Sara ya no aparece y Luis cambió de grupo.
    filas = [FILAS[0], _fila("152001000661", 9002, 1085000002.0, "DÍAZ", "LUIS", "7", "C")]
    _importar(_xlsx(tmp_path, filas, "corte2.xlsx"))
    sara.refresh_from_db()
    assert not sara.activo
    assert not PlantillaFacial.objects.filter(estudiante=sara).exists()
    assert Estudiante.objects.get(simat_per_id="9002").grupo == "C"


def test_dry_run_no_escribe(institucion, tmp_path):
    _importar(_xlsx(tmp_path, FILAS), "--dry-run")
    assert not Estudiante.objects.exists()


def test_institucion_debe_ser_unica(institucion, otra_institucion, tmp_path):
    ruta = _xlsx(tmp_path, FILAS)
    with pytest.raises(CommandError):
        call_command("importar_estudiantes", ruta, "--dane", "152001000661", "--institucion", "e")


def test_dane_sin_estudiantes(institucion, tmp_path):
    with pytest.raises(CommandError):
        call_command(
            "importar_estudiantes",
            _xlsx(tmp_path, FILAS),
            "--dane",
            "000",
            "--institucion",
            "Normal",
        )


def test_archivo_sin_columnas(institucion, tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["ANO_INF", "CODIGO_DANE"])
    ruta = tmp_path / "malo.xlsx"
    wb.save(ruta)
    with pytest.raises(CommandError):
        _importar(str(ruta))
