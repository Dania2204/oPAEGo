"""API de estudiantes PAE y operaciones del lote sin conexión (rol SUPERVISOR)."""

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.estudiantes import servicios
from apps.estudiantes.models import EntregaEstudiante

from .conftest import cliente_api
from .test_estudiantes import _estudiante

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
    assert {"curso", "jornada", "codigo_qr", "entrega_del_dia"} <= set(fila)
    assert not {"autorizacion_vigente", "rostro_inscrito"} & set(fila)
    por_id = {e.pk: e for e in curso}
    assert fila["codigo_qr"] == por_id[fila["id"]].codigo_qr


def test_filtros_por_curso_y_busqueda(api_supervisor, curso):
    assert api_supervisor.get(URL, {"grado": "7", "grupo": "B"}).data["count"] == 3
    assert api_supervisor.get(URL, {"q": "rosero"}).data["count"] == 4
    assert api_supervisor.get(URL, {"q": "10P11"}).data["count"] == 1


def test_lista_sin_consultas_n_mas_1(api_supervisor, supervisor, curso):
    servicios.registrar_entrega(supervisor, curso[0], metodo="MANUAL", motivo="x")
    with CaptureQueriesContext(connection) as pocas:
        api_supervisor.get(URL)
    for i in range(20):
        _estudiante(curso[0].institucion, per_id=f"N{i}")
    with CaptureQueriesContext(connection) as muchas:
        api_supervisor.get(URL)
    assert len(muchas) == len(pocas)


def test_institucion_consulta_pero_no_recibe_el_codigo_qr(api_institucion, curso):
    r = api_institucion.get(URL)
    assert r.data["count"] == 4
    assert all(fila["codigo_qr"] is None for fila in r.data["results"])


def test_ya_no_hay_plantillas(api_supervisor, curso):
    assert api_supervisor.get(URL + "plantillas/", {"grado": "7"}).status_code == 404


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


def test_historial_del_supervisor(api_supervisor, supervisor, admin, curso):
    servicios.registrar_entrega(supervisor, curso[0], metodo="MANUAL", motivo="x")
    servicios.registrar_entrega(admin, curso[1], metodo="MANUAL", motivo="lo marcó el admin")
    r = api_supervisor.get(URL + "historial/")
    assert [e["estudiante"] for e in r.data["results"]] == [curso[0].pk]
    hoy = timezone.localdate().isoformat()
    assert cliente_api(admin).get(URL + "historial/", {"desde": hoy}).data["count"] == 2


# ------------------------------------------------------------ lote offline
def test_flujo_completo_por_el_lote(api_supervisor, curso):
    operaciones = [
        op(
            "estudiante.entregar",
            {"estudiante": curso[0].pk, "metodo": "QR", "codigo": curso[0].contenido_qr},
            5,
        ),
        op(
            "estudiante.entregar", {"estudiante": curso[1].pk, "metodo": "MANUAL", "motivo": "x"}, 4
        ),
    ]
    r = api_supervisor.post(LOTE, {"operaciones": operaciones}, format="json")
    assert r.status_code == 200
    assert [x["resultado"] for x in r.data["resultados"]] == ["ok"] * 2
    assert EntregaEstudiante.objects.count() == 2
    assert EntregaEstudiante.objects.get(estudiante=curso[0]).diferido
    # Reenviar el mismo lote no duplica nada.
    r = api_supervisor.post(LOTE, {"operaciones": operaciones}, format="json")
    assert [x["resultado"] for x in r.data["resultados"]] == ["duplicado"] * 2
    assert EntregaEstudiante.objects.count() == 2


def test_qr_equivocado_por_el_lote_se_rechaza(api_supervisor, curso):
    datos = {"estudiante": curso[0].pk, "metodo": "QR", "codigo": curso[1].contenido_qr}
    r = api_supervisor.post(
        LOTE, {"operaciones": [op("estudiante.entregar", datos)]}, format="json"
    )
    assert r.data["resultados"][0]["resultado"] == "rechazado"
    assert not EntregaEstudiante.objects.exists()


def test_segunda_entrega_del_dia_se_rechaza(api_supervisor, curso):
    datos = {"estudiante": curso[0].pk, "metodo": "MANUAL", "motivo": "x"}
    r = api_supervisor.post(
        LOTE,
        {"operaciones": [op("estudiante.entregar", datos), op("estudiante.entregar", datos)]},
        format="json",
    )
    assert [x["resultado"] for x in r.data["resultados"]] == ["ok", "rechazado"]


@pytest.mark.parametrize(
    "tipo", ["estudiante.autorizar", "estudiante.inscribir", "estudiante.revocar"]
)
def test_operaciones_biometricas_ya_no_existen(api_supervisor, curso, tipo):
    r = api_supervisor.post(
        LOTE, {"operaciones": [op(tipo, {"estudiante": curso[0].pk})]}, format="json"
    )
    assert r.status_code == 400  # tipo de operación desconocido


def test_estudiante_inexistente(api_supervisor, curso):
    datos = {"estudiante": 99999, "metodo": "MANUAL", "motivo": "x"}
    r = api_supervisor.post(
        LOTE, {"operaciones": [op("estudiante.entregar", datos)]}, format="json"
    )
    assert r.data["resultados"][0]["resultado"] == "rechazado"


def test_configuracion_publica_los_parametros(api_supervisor):
    r = api_supervisor.get("/api/sincronizacion/configuracion/")
    assert "estudiante.entregar" in r.data["operaciones"]
    assert r.data["prefijo_qr"] == "PAEGO-E1:"
    assert "estudiante.inscribir" not in r.data["operaciones"]
    assert "umbral_similitud_facial" not in r.data


def test_perfil_del_supervisor_trae_su_institucion(api_supervisor, institucion):
    r = api_supervisor.get("/api/auth/yo/")
    assert r.data["rol"] == "SUPERVISOR"
    assert r.data["institucion_id"] == institucion.pk
