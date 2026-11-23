"""Asistente de reportes del administrador (Claude con herramientas de solo lectura).

Ninguna prueba llama a la API real: un cliente falso devuelve mensajes con la
forma exacta del SDK de Anthropic (BetaMessage).
"""

import json
from datetime import timedelta

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage
from django.urls import reverse
from django.utils import timezone

from apps.asistente import herramientas, servicios
from apps.asistente.models import ConversacionAsistente
from apps.asistente.templatetags.asistente import md_seguro
from apps.auditoria.models import Accion, RegistroAuditoria
from apps.envios.models import Novedad
from apps.estudiantes import servicios as servicios_estudiantes
from apps.monitoreo import kpis

from .test_estudiantes import _estudiante

URL = "/asistente/"


def _rango():
    hoy = timezone.localdate()
    return {"desde": str(hoy - timedelta(days=1)), "hasta": str(hoy + timedelta(days=1))}


# ------------------------------------------------------------ cliente falso
def _mensaje(contenido, motivo):
    return BetaMessage.model_validate(
        {
            "id": "msg_prueba",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": contenido,
            "stop_reason": motivo,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_input_tokens": 900,
                "cache_creation_input_tokens": 0,
            },
        }
    )


def _pide(nombre, entrada, id_="toolu_1"):
    return _mensaje(
        [
            {"type": "thinking", "thinking": "", "signature": "firma"},
            {"type": "tool_use", "id": id_, "name": nombre, "input": entrada},
        ],
        "tool_use",
    )


def _responde(texto):
    return _mensaje([{"type": "text", "text": texto}], "end_turn")


class _Flujo:
    def __init__(self, mensaje):
        self.mensaje = mensaje

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.mensaje


class ClienteFalso:
    """Devuelve las respuestas en orden y guarda lo que se le envió."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []
        self.beta = self
        self.messages = self

    def stream(self, **parametros):
        self.peticiones.append(json.loads(json.dumps(parametros, default=str)))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Flujo(r)


@pytest.fixture
def con_clave(settings):
    settings.ANTHROPIC_API_KEY = "sk-ant-prueba"


@pytest.fixture
def falso(monkeypatch, con_clave):
    def instalar(*respuestas):
        cliente = ClienteFalso(*respuestas)
        monkeypatch.setattr(servicios, "_cliente", lambda: cliente)
        return cliente

    return instalar


def _error_api(clase, status):
    peticion = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return clase("falla", response=httpx2.Response(status, request=peticion), body=None)


# -------------------------------------------------------------- servicio
def test_responde_usando_una_herramienta(falso, envio):
    cliente = falso(
        _pide("listar_envios", _rango()),
        _responde("Hay **1** envío asignado."),
    )
    r = servicios.preguntar([], "¿Cuántos envíos hay?")
    assert r.completo and r.texto == "Hay **1** envío asignado."
    assert r.consultas == [
        {
            "herramienta": "listar_envios",
            "entrada": _rango(),
            "error": False,
        }
    ]
    # usuario, asistente (tool_use), usuario (tool_result), asistente (texto)
    assert [m["role"] for m in r.mensajes] == ["user", "assistant", "user", "assistant"]
    resultado = r.mensajes[2]["content"][0]
    assert resultado["type"] == "tool_result" and resultado["tool_use_id"] == "toolu_1"
    assert json.loads(resultado["content"])["total"] == 1
    # El bloque de razonamiento se guarda tal cual (debe reenviarse sin cambios).
    assert r.mensajes[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "firma"}
    assert r.uso["cache_read_input_tokens"] == 1800

    primera = cliente.peticiones[0]
    assert primera["model"] == "claude-opus-5-5"
    assert primera["thinking"] == {"type": "adaptive"}
    assert primera["fallbacks"] == "default"
    assert primera["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Hoy es" in primera["system"][1]["text"]
    assert [h["name"] for h in primera["tools"]] == list(herramientas.HERRAMIENTAS)
    # La segunda vuelta reenvía la conversación con el resultado.
    assert len(cliente.peticiones[1]["messages"]) == 3


def test_error_de_herramienta_vuelve_a_claude(falso, db):
    falso(_pide("detalle_envio", {"codigo": "NO-EXISTE"}), _responde("No encontré ese envío."))
    r = servicios.preguntar([], "¿Cómo va el envío NO-EXISTE?")
    resultado = r.mensajes[2]["content"][0]
    assert resultado["is_error"] is True and "No existe" in resultado["content"]
    assert r.consultas[0]["error"] is True


def test_rechazo_no_guarda_el_turno(falso, db):
    falso(_mensaje([], "refusal"))
    r = servicios.preguntar([{"role": "user", "content": "hola"}], "otra")
    assert not r.completo and "No puedo responder" in r.texto
    assert r.mensajes == [{"role": "user", "content": "hola"}]


def test_demasiadas_vueltas(falso, db):
    falso(*[_pide("situacion_actual", {}, f"t{i}") for i in range(servicios.MAX_VUELTAS)])
    r = servicios.preguntar([], "¿?")
    assert not r.completo and "demasiadas consultas" in r.texto


def test_sin_clave(settings, db):
    settings.ANTHROPIC_API_KEY = ""
    with pytest.raises(servicios.AsistenteNoConfigurado):
        servicios.preguntar([], "hola")


@pytest.mark.parametrize(
    ("error", "texto"),
    [
        (_error_api(anthropic.AuthenticationError, 401), "no es válida"),
        (_error_api(anthropic.RateLimitError, 429), "ocupado"),
        (_error_api(anthropic.InternalServerError, 500), "no respondió"),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com")
            ),
            "conexión",
        ),
    ],
)
def test_errores_de_la_api(falso, db, error, texto):
    falso(error)
    with pytest.raises(servicios.AsistenteError, match=texto):
        servicios.preguntar([], "hola")


# ------------------------------------------------------------- panel web
def test_chat_flujo_completo(web_admin, admin, falso, envio):
    r = web_admin.get(URL)
    html = r.content.decode()
    assert r.status_code == 200 and "Asistente de reportes" in html
    assert "no está configurado" not in html and "Dame el reporte" in html

    falso(
        _pide("indicadores", {"desde": "2026-11-01", "hasta": "2026-11-07"}),
        _responde("- Entregas: **0**\n\n| Estado | Envíos |\n|---|---|\n| Asignado | 1 |"),
    )
    r = web_admin.post(URL, {"pregunta": "¿Cómo vamos?"}, HTTP_HX_REQUEST="true")
    html = r.content.decode()
    assert r.status_code == 200
    assert "<li>Entregas: <strong>0</strong></li>" in html and "<td>Asignado</td>" in html
    assert "Consultó: indicadores (2026-11-01 a 2026-11-07)" in html
    conversacion = ConversacionAsistente.objects.get()
    assert conversacion.usuario == admin and conversacion.titulo == "¿Cómo vamos?"
    assert len(conversacion.turnos) == 1 and len(conversacion.mensajes) == 4
    assert r["HX-Replace-Url"] == f"{URL}?c={conversacion.pk}"
    assert f'value="{conversacion.pk}" hx-swap-oob="true"' in html

    registro = RegistroAuditoria.objects.get(accion=Accion.ASISTENTE_CONSULTA)
    assert registro.usuario == admin and registro.datos["herramientas"] == ["indicadores"]
    assert registro.datos["uso"]["output_tokens"] == 40

    # Segunda pregunta en la misma conversación: reenvía el historial.
    cliente = falso(_responde("Sigue igual."))
    web_admin.post(
        URL, {"pregunta": "¿Y ahora?", "conversacion": conversacion.pk}, HTTP_HX_REQUEST="true"
    )
    assert len(cliente.peticiones[0]["messages"]) == 5
    conversacion.refresh_from_db()
    assert len(conversacion.turnos) == 2

    # La conversación se puede reabrir y borrar.
    html = web_admin.get(URL, {"c": conversacion.pk}).content.decode()
    assert "Sigue igual." in html and "Borrar esta conversación" in html
    web_admin.post(URL, {"conversacion": conversacion.pk, "accion": "borrar"})
    assert not ConversacionAsistente.objects.exists()


def test_chat_sin_clave_avisa(web_admin, settings):
    settings.ANTHROPIC_API_KEY = ""
    assert "no está configurado" in web_admin.get(URL).content.decode()
    r = web_admin.post(URL, {"pregunta": "hola"}, HTTP_HX_REQUEST="true")
    assert r.status_code == 200 and "ANTHROPIC_API_KEY" in r.content.decode()
    assert not ConversacionAsistente.objects.exists()


def test_chat_error_de_la_api(web_admin, falso):
    falso(_error_api(anthropic.InternalServerError, 500))
    r = web_admin.post(URL, {"pregunta": "hola"}, HTTP_HX_REQUEST="true")
    assert "no respondió" in r.content.decode()
    assert not ConversacionAsistente.objects.exists()


def test_chat_cuota_por_hora(web_admin, falso, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "asistente": "1/hour",
        },
    }
    falso(_responde("Hola."))
    web_admin.post(URL, {"pregunta": "hola"}, HTTP_HX_REQUEST="true")
    r = web_admin.post(URL, {"pregunta": "otra"}, HTTP_HX_REQUEST="true")
    assert "máximo de preguntas por hora" in r.content.decode()


def test_pregunta_vacia_y_sin_htmx(web_admin, falso):
    r = web_admin.post(URL, {"pregunta": "   "}, HTTP_HX_REQUEST="true")
    assert "Escriba una pregunta" in r.content.decode()
    falso(_responde("Hola."))
    r = web_admin.post(URL, {"pregunta": "hola"})
    assert r.status_code == 302 and "?c=" in r["Location"]


def test_conversacion_ajena_no_se_ve(web_admin, conductor):
    ajena = ConversacionAsistente.objects.create(usuario=conductor.usuario, titulo="x")
    assert web_admin.get(URL, {"c": ajena.pk}).status_code == 404


def test_solo_el_administrador(client, conductor):
    from django.conf import settings

    from apps.cuentas.tokens import emitir_tokens

    client.cookies[settings.JWT_COOKIE_ACCESS] = emitir_tokens(conductor.usuario)["access"]
    assert client.get(URL).status_code == 403
    assert client.post(URL, {"pregunta": "hola"}).status_code == 403


def test_menu_tiene_el_asistente(web_admin):
    html = web_admin.get(reverse("monitoreo:indicadores")).content.decode()
    assert 'href="/asistente/"' in html


# ---------------------------------------------------------- herramientas
def _json(nombre, entrada):
    texto, error = herramientas.ejecutar(nombre, entrada)
    assert not error, texto
    return json.loads(texto)


def test_indicadores_coinciden_con_el_panel(envio, institucion, conductor):
    hoy = timezone.localdate().isoformat()
    datos = _json("indicadores", {"desde": hoy, "hasta": hoy, "agrupar_por": "institucion"})
    esperado = kpis.calcular(timezone.localdate(), timezone.localdate())
    assert datos["total"] == json.loads(json.dumps(esperado.como_dict()))
    assert datos["por_institucion"][0]["institucion"] == "Escuela Normal Superior"
    por_conductor = _json(
        "indicadores", {"desde": hoy, "hasta": hoy, "agrupar_por": "conductor", "conductor": "carl"}
    )
    assert por_conductor["filtros"]["conductor"] == por_conductor["por_conductor"][0]["conductor"]
    assert len(_json("indicadores", {"agrupar_por": "semana"})["por_semana"]) >= 4


def test_listar_y_detalle_de_envio(envio, institucion):
    datos = _json("listar_envios", {"institucion": "normal", "estados": ["ASIGNADO"]})
    hoy = timezone.localdate()
    if envio.programado_para.date() <= hoy:  # por defecto, los últimos 7 días hasta hoy
        assert datos["total"] == 1
    datos = _json("listar_envios", {**_rango(), "codigo": envio.codigo})
    assert datos["envios"][0]["codigo"] == envio.codigo
    detalle = _json("detalle_envio", {"codigo": envio.codigo.lower()})
    assert detalle["items"][0]["producto"] == "Leche" and detalle["evidencia"] == {
        "registrada": False
    }


def test_novedades_por_conductor(envio, conductor):
    Novedad.objects.create(
        envio=envio,
        reportado_por=conductor.usuario,
        origen=Novedad.Origen.TRAYECTO,
        tipo=Novedad.Tipo.RETRASO,
        descripcion="Trancón en la Panamericana. " * 30,
        ocurrido_en=timezone.now(),
    )
    datos = _json("novedades", {"solo_pendientes": True})
    assert datos["total"] == 1 and datos["por_tipo"] == {"Retraso": 1}
    assert list(datos["por_conductor"].values()) == [1]
    assert len(datos["novedades"][0]["descripcion"]) <= herramientas.TEXTO_MAX


def test_situacion_actual(envio_en_transito):
    datos = _json("situacion_actual", {})
    assert datos["en_transito"][0]["codigo"] == envio_en_transito.codigo


def test_cobertura_solo_conteos(institucion, supervisor):
    ana = _estudiante(institucion, "P1")
    _estudiante(institucion, "P2", nombres="Luis", grupo="A")
    servicios_estudiantes.registrar_entrega(supervisor, ana, metodo="MANUAL", motivo="Sin carné")
    hoy = timezone.localdate().isoformat()
    datos = _json("cobertura_pae", {"institucion": "Normal", "fecha": hoy, "por_curso": True})
    assert datos["estudiantes_activos"] == 2
    assert datos["dias_con_entregas"] == [{"fecha": hoy, "recibieron": 1, "porcentaje": 50.0}]
    assert {c["curso"] for c in datos["por_curso"]} == {"7° A", "7° B"}
    texto = json.dumps(datos, ensure_ascii=False)
    # Ley 1581: ni nombres ni documentos de estudiantes.
    for dato in ("Ana", "Rosero", "Luis", ana.numero_documento):
        assert dato not in texto


def test_auditoria_oculta_datos_de_estudiantes(institucion, supervisor):
    ana = _estudiante(institucion, "P1")
    servicios_estudiantes.registrar_entrega(supervisor, ana, metodo="MANUAL", motivo="Sin carné")
    datos = _json("auditoria", {"accion": "ENTREGA_ESTUDIANTE"})
    assert datos["total"] == 1 and "Ana" not in json.dumps(datos, ensure_ascii=False)


def test_catalogo_matricula_y_enlace(institucion, otra_institucion, conductor, vehiculo):
    assert _json("catalogo", {"tipo": "instituciones"})["total"] == 2
    assert _json("catalogo", {"tipo": "conductores", "buscar": "carl"})["total"] == 1
    assert _json("catalogo", {"tipo": "vehiculos"})["filas"][0]["placa"] == "ABC123"
    assert _json("matricula_simat", {})["total"] == 0
    enlace = _json(
        "enlace_reporte", {"desde": "2026-10-01", "hasta": "2026-10-31", "institucion": "otra"}
    )
    assert enlace["pdf"] == (
        f"/reportes/?desde=2026-10-01&hasta=2026-10-31&institucion={otra_institucion.pk}"
        "&formato=pdf"
    )


def test_errores_de_herramientas(institucion, otra_institucion):
    casos = [
        ("no_existe", {}, "no existe"),
        ("catalogo", {"tipo": "otra"}, "tipo debe ser"),
        ("indicadores", {"desde": "ayer"}, "Fecha inválida"),
        ("indicadores", {"desde": "2026-02-01", "hasta": "2026-01-01"}, "posterior"),
        ("indicadores", {"desde": "2020-01-01", "hasta": "2026-01-01"}, "demasiado largo"),
        ("indicadores", {"institucion": "zzz"}, "ninguna institución"),
        ("indicadores", {"institucion": "Principal"}, "Varias instituciones"),
        ("indicadores", {"conductor": "zzz"}, "ningún conductor"),
    ]
    for nombre, entrada, texto in casos:
        salida, error = herramientas.ejecutar(nombre, entrada)
        assert error and texto in salida, (nombre, salida)
    assert herramientas.ejecutar("catalogo", "x")[1] is True


def test_definiciones_estables():
    defs = herramientas.definiciones()
    assert defs == herramientas.definiciones()  # mismo orden: no rompe la caché
    for d in defs:
        assert d["input_schema"]["additionalProperties"] is False


# ---------------------------------------------------------------- markdown
def test_markdown_seguro():
    html = md_seguro(
        "Hola <script>x</script> **bien**\n\n- uno\n- [PDF](/reportes/?a=1&b=2)\n"
        "1. [malo](https://evil.co)\n\n| a | b |\n|---|---|\n| 1 | `c` |"
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<strong>bien</strong>" in html
    assert '<a href="/reportes/?a=1&amp;b=2">PDF</a>' in html
    assert "evil.co" not in html and "<li>malo</li>" in html
    assert "<th>a</th>" in html and "<td><code>c</code></td>" in html
    assert md_seguro("") == ""
