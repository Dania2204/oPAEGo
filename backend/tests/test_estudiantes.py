"""Entrega del PAE a estudiantes: autorización, rostro cifrado y entrega diaria."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.cuentas.models import Rol
from apps.estudiantes import cifrado, servicios
from apps.estudiantes.models import (
    EntregaEstudiante,
    EntregaInmutableError,
    Estudiante,
    MetodoEntrega,
    PlantillaFacial,
)

from .conftest import crear_usuario


def _vector(semilla, dimension=192):
    return [((i * 7 + semilla * 13) % 17 - 8) / 8 for i in range(dimension)]


MUESTRAS = [_vector(1), _vector(2), _vector(3)]
ACUDIENTE = {
    "acudiente_nombre": "Rosa Pérez",
    "acudiente_documento": "27000111",
    "parentesco": "Madre",
}


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


@pytest.fixture
def inscrito(supervisor, estudiante):
    servicios.autorizar(supervisor, estudiante, **ACUDIENTE)
    servicios.inscribir_rostro(supervisor, estudiante, vectores=MUESTRAS, modelo="mobilefacenet-v1")
    return estudiante


# ---------------------------------------------------------------- cifrado
def test_vector_se_guarda_cifrado_y_se_recupera(inscrito):
    plantilla = PlantillaFacial.objects.filter(estudiante=inscrito).first()
    assert plantilla.dimension == 192
    assert "0.125" not in plantilla.vector_cifrado  # no hay números en claro
    recuperado = plantilla.vector
    assert recuperado == pytest.approx(MUESTRAS[0], abs=1e-6)


def test_sin_la_clave_la_plantilla_no_se_lee(inscrito):
    plantilla = PlantillaFacial.objects.filter(estudiante=inscrito).first()
    otra = "q1E0sY0bLbH7rZ2m3fJr9Q4xP6tN8wK5uV1yA2cD3eE="
    with override_settings(BIOMETRIA_CLAVE=otra), pytest.raises(cifrado.VectorInvalido):
        _ = plantilla.vector
    with override_settings(BIOMETRIA_CLAVE=""), pytest.raises(cifrado.BiometriaNoConfigurada):
        _ = plantilla.vector


def test_similitud_coseno():
    assert cifrado.similitud_coseno(_vector(1), _vector(1)) == pytest.approx(1.0)
    assert cifrado.similitud_coseno([1, 0], [0, 1]) == pytest.approx(0.0)


@pytest.mark.parametrize("malo", [[1.0] * 10, ["a"] * 128, [float("nan")] * 128, [0.0] * 128])
def test_vectores_invalidos(malo):
    with pytest.raises(cifrado.VectorInvalido):
        cifrado.validar_vector(malo)


# ------------------------------------------------- autorización e inscripción
def test_no_se_inscribe_sin_autorizacion(supervisor, estudiante):
    with pytest.raises(ValidationError):
        servicios.inscribir_rostro(supervisor, estudiante, vectores=MUESTRAS, modelo="m")
    assert not PlantillaFacial.objects.exists()


@pytest.mark.parametrize("n", [2, 6])
def test_numero_de_muestras(supervisor, estudiante, n):
    servicios.autorizar(supervisor, estudiante, **ACUDIENTE)
    with pytest.raises(ValidationError):
        servicios.inscribir_rostro(
            supervisor, estudiante, vectores=[_vector(i) for i in range(n)], modelo="m"
        )


def test_autorizacion_exige_datos_y_no_se_duplica(supervisor, estudiante):
    with pytest.raises(ValidationError):
        servicios.autorizar(supervisor, estudiante, **{**ACUDIENTE, "parentesco": " "})
    servicios.autorizar(supervisor, estudiante, **ACUDIENTE)
    with pytest.raises(ValidationError):
        servicios.autorizar(supervisor, estudiante, **ACUDIENTE)


def test_reinscribir_reemplaza_las_muestras(inscrito, supervisor):
    servicios.inscribir_rostro(supervisor, inscrito, vectores=MUESTRAS + [_vector(4)], modelo="m")
    assert inscrito.plantillas.count() == 4


def test_revocar_borra_las_plantillas_y_queda_auditado(inscrito, supervisor):
    servicios.revocar_autorizacion(supervisor, inscrito, motivo="Lo pidió la madre")
    inscrito.refresh_from_db()
    assert inscrito.autorizacion_vigente is None
    assert not PlantillaFacial.objects.filter(estudiante=inscrito).exists()
    acciones = set(RegistroAuditoria.objects.values_list("accion", flat=True))
    assert {Accion.AUTORIZACION_REVOCADA, Accion.ROSTRO_BORRADO} <= acciones
    # Se puede volver a autorizar más adelante.
    servicios.autorizar(supervisor, inscrito, **ACUDIENTE)
    inscrito.refresh_from_db()
    assert inscrito.autorizacion_vigente is not None


def test_la_auditoria_no_guarda_el_vector(inscrito):
    for registro in RegistroAuditoria.objects.all():
        assert "vector" not in str(registro.datos)


def test_dar_de_baja_borra_plantillas(inscrito):
    servicios.dar_de_baja(inscrito)
    inscrito.refresh_from_db()
    assert not inscrito.activo
    assert not inscrito.plantillas.exists()


# ----------------------------------------------------------------- permisos
def test_supervisor_de_otra_institucion_no_accede(supervisor_otra, estudiante):
    with pytest.raises(PermissionDenied):
        servicios.autorizar(supervisor_otra, estudiante, **ACUDIENTE)
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


def test_solo_el_supervisor_inscribe_rostros(admin, estudiante):
    servicios.autorizar(admin, estudiante, **ACUDIENTE)
    with pytest.raises(PermissionDenied):
        servicios.inscribir_rostro(admin, estudiante, vectores=MUESTRAS, modelo="m")


# ------------------------------------------------------------------ entrega
def test_entrega_facial(inscrito, supervisor):
    entrega = servicios.registrar_entrega(supervisor, inscrito, metodo="FACIAL", similitud=0.93)
    assert entrega.metodo == MetodoEntrega.FACIAL
    assert entrega.fecha == timezone.localdate()
    assert RegistroAuditoria.objects.filter(accion=Accion.ENTREGA_ESTUDIANTE).count() == 1


def test_entrega_facial_bajo_el_umbral_se_rechaza(inscrito, supervisor):
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, inscrito, metodo="FACIAL", similitud=0.5)


def test_entrega_facial_sin_rostro_se_rechaza(supervisor, estudiante):
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="FACIAL", similitud=0.99)


def test_entrega_manual_exige_motivo(supervisor, estudiante):
    with pytest.raises(ValidationError):
        servicios.registrar_entrega(supervisor, estudiante, metodo="MANUAL", motivo="  ")
    entrega = servicios.registrar_entrega(
        supervisor, estudiante, metodo="MANUAL", motivo="Sin autorización biométrica"
    )
    assert entrega.similitud is None


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


def test_biometria_no_configurada_responde_503(supervisor, estudiante):
    servicios.autorizar(supervisor, estudiante, **ACUDIENTE)
    with override_settings(BIOMETRIA_CLAVE=""), pytest.raises(servicios.BiometriaNoDisponible):
        servicios.inscribir_rostro(supervisor, estudiante, vectores=MUESTRAS, modelo="m")
    assert not PlantillaFacial.objects.exists()


def test_plantillas_de_un_curso(inscrito, institucion):
    otro = _estudiante(institucion, per_id="P2")
    resultado = servicios.plantillas_de(Estudiante.objects.filter(pk__in=[inscrito.pk, otro.pk]))
    assert list(resultado) == [inscrito.pk]
    assert len(resultado[inscrito.pk]) == 3


def test_curso_legible(estudiante):
    assert estudiante.curso == "7° B"
    assert estudiante.nombre_completo == "Ana María Rosero Díaz"
