"""API de estudiantes PAE y operaciones del lote sin conexión (rol SUPERVISOR)."""

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.estudiantes import servicios
from apps.estudiantes.models import EntregaEstudiante, PlantillaFacial

from .conftest import cliente_api
from .test_estudiantes import ACUDIENTE, MUESTRAS, _estudiante, _vector

URL = "/api/estudiantes/"
LOTE = "/api/sincronizacion/lote/"


def op(tipo, datos, hace_min=0, uid=None):
    return {
        "uuid_cliente": str(uid or uuid.uuid4()),
        "tipo": tipo,
        "ocurrido_en": (timezone.now() - timedelta(minutes=hace_min)).isoformat(),
        "datos": datos,
    }


@pytest.fixture
def api_supervisor(supervisor):
    return cliente_api(supervisor)


@pytest.fixture
def curso(institucion, otra_institucion):
    """7°B con 3 estudiantes, 1 de 11°A y uno de otra institución."""
    estudiantes = [_estudiante(institucion, per_id=f"P{i}") for i in range(3)]
    estudiantes.append(_estudiante(institucion, per_id="P11", grado="11", grupo="A"))
    _estudiante(otra_institucion, per_id="X1")
    return estudiantes


def test_supervisor_lista_solo_su_institucion(api_supervisor, curso):
    r = api_supervisor.get(URL)
    assert r.status_code == 200
    assert r.data["count"] == 4
    fila = r.data["results"][0]
    assert {"curso", "autorizacion_vigente", "rostro_inscrito", "entrega_del_dia"} <= set(fila)


def test_filtros_por_curso_y_busqueda(api_supervisor, curso):
    assert api_supervisor.get(URL, {"grado": "7", "grupo": "B"}).data["count"] == 3
    assert api_supervisor.get(URL, {"q": "rosero"}).data["count"] == 4
    assert api_supervisor.get(URL, {"q": "10P11"}).data["count"] == 1


def test_lista_sin_consultas_n_mas_1(api_supervisor, supervisor, curso):
    servicios.autorizar(supervisor, curso[0], **ACUDIENTE)
    servicios.inscribir_rostro(supervisor, curso[0], vectores=MUESTRAS, modelo="m")
    with CaptureQueriesContext(connection) as pocas:
        api_supervisor.get(URL)
    for i in range(20):
        _estudiante(curso[0].institucion, per_id=f"N{i}")
    with CaptureQueriesContext(connection) as muchas:
        api_supervisor.get(URL)
    assert len(muchas) == len(pocas)


def test_institucion_consulta_pero_no_descarga_plantillas(api_institucion, curso):
    assert api_institucion.get(URL).data["count"] == 4
    assert api_institucion.get(URL + "plantillas/", {"grado": "7"}).status_code == 403


def test_conductor_no_ve_estudiantes(api_conductor, curso):
    assert api_conductor.get(URL).status_code == 403


def test_resumen_de_cursos(api_supervisor, supervisor, curso):
    servicios.registrar_entrega(supervisor, curso[0], metodo="MANUAL", motivo="x")
    r = api_supervisor.get(URL + "cursos/")
    assert r.status_code == 200
    assert r.data["cobertura"] == {"activos": 4, "recibieron": 1, "porcentaje": 25.0}
    septimo = next(c for c in r.data["cursos"] if c["grado"] == "7")
    assert (septimo["curso"], septimo["activos"], septimo["recibieron"]) == ("7° B", 3, 1)
    # Otro día no cuenta.
    ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
    assert api_supervisor.get(URL + "cursos/", {"fecha": ayer}).data["cobertura"]["recibieron"] == 0
    assert api_supervisor.get(URL + "cursos/", {"fecha": "ayer"}).status_code == 400


def test_plantillas_del_curso(api_supervisor, supervisor, curso):
    servicios.autorizar(supervisor, curso[0], **ACUDIENTE)
    servicios.inscribir_rostro(supervisor, curso[0], vectores=MUESTRAS, modelo="m")
    assert api_supervisor.get(URL + "plantillas/").status_code == 400
    r = api_supervisor.get(URL + "plantillas/", {"grado": "7", "grupo": "B"})
    assert r.status_code == 200
    assert [p["estudiante"] for p in r.data["plantillas"]] == [curso[0].pk]
    assert len(r.data["plantillas"][0]["vectores"]) == 3
    assert r.data["plantillas"][0]["vectores"][0] == pytest.approx(MUESTRAS[0], abs=1e-6)


def test_historial_del_supervisor(api_supervisor, supervisor, admin, curso):
    servicios.registrar_entrega(supervisor, curso[0], metodo="MANUAL", motivo="x")
    servicios.registrar_entrega(admin, curso[1], metodo="MANUAL", motivo="lo marcó el admin")
    r = api_supervisor.get(URL + "historial/")
    assert [e["estudiante"] for e in r.data["results"]] == [curso[0].pk]
    hoy = timezone.localdate().isoformat()
    assert cliente_api(admin).get(URL + "historial/", {"desde": hoy}).data["count"] == 2


# ------------------------------------------------------------ lote offline
def test_flujo_completo_por_el_lote(api_supervisor, curso):
    est = curso[0].pk
    operaciones = [
        op("estudiante.autorizar", {"estudiante": est, **ACUDIENTE}, 30),
        op("estudiante.inscribir", {"estudiante": est, "vectores": MUESTRAS, "modelo": "m"}, 29),
        op("estudiante.entregar", {"estudiante": est, "metodo": "FACIAL", "similitud": 0.91}, 5),
        op(
            "estudiante.entregar", {"estudiante": curso[1].pk, "metodo": "MANUAL", "motivo": "x"}, 4
        ),
    ]
    r = api_supervisor.post(LOTE, {"operaciones": operaciones}, format="json")
    assert r.status_code == 200
    assert [x["resultado"] for x in r.data["resultados"]] == ["ok"] * 4
    assert PlantillaFacial.objects.filter(estudiante_id=est).count() == 3
    assert EntregaEstudiante.objects.count() == 2
    # Reenviar el mismo lote no duplica nada.
    r = api_supervisor.post(LOTE, {"operaciones": operaciones}, format="json")
    assert [x["resultado"] for x in r.data["resultados"]] == ["duplicado"] * 4
    assert EntregaEstudiante.objects.count() == 2


def test_segunda_entrega_del_dia_se_rechaza(api_supervisor, curso):
    datos = {"estudiante": curso[0].pk, "metodo": "MANUAL", "motivo": "x"}
    r = api_supervisor.post(
        LOTE,
        {"operaciones": [op("estudiante.entregar", datos), op("estudiante.entregar", datos)]},
        format="json",
    )
    assert [x["resultado"] for x in r.data["resultados"]] == ["ok", "rechazado"]


def test_inscripcion_sin_autorizacion_se_rechaza(api_supervisor, curso):
    datos = {"estudiante": curso[0].pk, "vectores": [_vector(i) for i in range(3)], "modelo": "m"}
    r = api_supervisor.post(
        LOTE, {"operaciones": [op("estudiante.inscribir", datos)]}, format="json"
    )
    assert r.data["resultados"][0]["resultado"] == "rechazado"


def test_revocar_por_el_lote(api_supervisor, supervisor, curso):
    servicios.autorizar(supervisor, curso[0], **ACUDIENTE)
    servicios.inscribir_rostro(supervisor, curso[0], vectores=MUESTRAS, modelo="m")
    datos = {"estudiante": curso[0].pk, "motivo": "Lo pidió el acudiente"}
    r = api_supervisor.post(LOTE, {"operaciones": [op("estudiante.revocar", datos)]}, format="json")
    assert r.data["resultados"][0]["resultado"] == "ok"
    assert not PlantillaFacial.objects.exists()


def test_estudiante_inexistente(api_supervisor, curso):
    datos = {"estudiante": 99999, "metodo": "MANUAL", "motivo": "x"}
    r = api_supervisor.post(
        LOTE, {"operaciones": [op("estudiante.entregar", datos)]}, format="json"
    )
    assert r.data["resultados"][0]["resultado"] == "rechazado"


def test_configuracion_publica_los_parametros(api_supervisor):
    r = api_supervisor.get("/api/sincronizacion/configuracion/")
    assert "estudiante.entregar" in r.data["operaciones"]
    assert r.data["biometria_disponible"] is True
    assert r.data["umbral_similitud_facial"] == 0.80
    assert (r.data["muestras_rostro_min"], r.data["muestras_rostro_max"]) == (3, 5)
