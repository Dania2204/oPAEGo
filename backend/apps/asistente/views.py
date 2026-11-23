from django.conf import settings
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.comun import es_htmx, responder
from apps.cuentas.limite import LimitePorUsuario
from apps.cuentas.permisos import AdministradorRequeridoMixin

from . import servicios
from .models import ConversacionAsistente

MAX_PREGUNTA = 1500
MAX_TURNOS = 20

EJEMPLOS = [
    "¿Cómo van los indicadores de esta semana comparados con la anterior?",
    "¿Qué conductor tuvo más novedades este mes y de qué tipo?",
    "¿Qué porcentaje de estudiantes recibió el PAE ayer, por curso?",
    "¿Hay envíos retrasados en este momento?",
    "Dame el reporte de envíos de octubre en PDF.",
]

NOMBRES = {
    "indicadores": "indicadores",
    "listar_envios": "envíos",
    "detalle_envio": "detalle de envío",
    "novedades": "novedades",
    "situacion_actual": "situación actual",
    "cobertura_pae": "entrega PAE a estudiantes",
    "catalogo": "catálogo",
    "matricula_simat": "matrícula SIMAT",
    "auditoria": "auditoría",
    "enlace_reporte": "reporte PDF/Excel",
}


class _Limite(LimitePorUsuario):
    scope = "asistente"


def _resumen_consultas(consultas):
    """'indicadores (2026-11-01 a 2026-11-07, Normal Superior) · novedades'."""
    partes = []
    for c in consultas:
        entrada = c.get("entrada") or {}
        detalle = [
            str(v)
            for k in ("codigo", "fecha", "institucion", "conductor", "tipo")
            if (v := entrada.get(k))
        ]
        if entrada.get("desde") or entrada.get("hasta"):
            detalle.insert(0, f"{entrada.get('desde', '…')} a {entrada.get('hasta', 'hoy')}")
        nombre = NOMBRES.get(c.get("herramienta"), c.get("herramienta"))
        texto = f"{nombre} ({', '.join(detalle)})" if detalle else nombre
        if texto not in partes:
            partes.append(texto)
    return " · ".join(partes)


def _conversacion(request):
    pk = request.POST.get("conversacion") or request.GET.get("c")
    if pk and str(pk).isdigit():
        return get_object_or_404(ConversacionAsistente, pk=pk, usuario=request.user)
    return None


class AsistenteView(AdministradorRequeridoMixin, View):
    """Chat del administrador con el asistente de reportes (Claude)."""

    def get(self, request):
        conversacion = _conversacion(request)
        recientes = ConversacionAsistente.objects.filter(usuario=request.user).only(
            "id", "titulo", "actualizado_en"
        )[:15]
        return responder(
            request,
            "asistente/chat.html",
            {
                "conversacion": conversacion,
                "turnos": conversacion.turnos if conversacion else [],
                "recientes": recientes,
                "ejemplos": EJEMPLOS,
                "configurado": servicios.configurado(),
                "max_pregunta": MAX_PREGUNTA,
            },
        )

    def post(self, request):
        conversacion = _conversacion(request)
        if request.POST.get("accion") == "borrar" and conversacion:
            conversacion.delete()
            return redirect("asistente:chat")

        pregunta = " ".join((request.POST.get("pregunta") or "").split())[:MAX_PREGUNTA]
        if not pregunta:
            return self._turno(request, conversacion, None, "Escriba una pregunta.")
        if conversacion and len(conversacion.turnos) >= MAX_TURNOS:
            return self._turno(
                request,
                conversacion,
                pregunta,
                "Esta conversación ya es muy larga. Empiece una nueva conversación.",
            )
        limite = _Limite()
        if not limite.allow_request(request, self):
            minutos = max(1, round((limite.wait() or 60) / 60))
            return self._turno(
                request,
                conversacion,
                pregunta,
                f"Alcanzó el máximo de preguntas por hora. Intente en unos {minutos} min.",
            )

        try:
            resultado = servicios.preguntar(conversacion.mensajes if conversacion else [], pregunta)
        except servicios.AsistenteNoConfigurado:
            return self._turno(
                request,
                conversacion,
                pregunta,
                "El asistente no está configurado: falta la clave ANTHROPIC_API_KEY en el "
                "servidor.",
            )
        except servicios.AsistenteError as exc:
            return self._turno(request, conversacion, pregunta, str(exc))

        turno = {
            "pregunta": pregunta,
            "respuesta": resultado.texto,
            "consultas": _resumen_consultas(resultado.consultas),
            "en": timezone.now().isoformat(),
            "aviso": not resultado.completo,
        }
        if resultado.completo:
            if conversacion is None:
                conversacion = ConversacionAsistente(usuario=request.user, titulo=pregunta[:120])
            conversacion.mensajes = resultado.mensajes
            conversacion.turnos = [*conversacion.turnos, turno]
            conversacion.save()
        registrar(
            request.user,
            Accion.ASISTENTE_CONSULTA,
            f"Pregunta al asistente de reportes: {pregunta[:200]}",
            objeto=conversacion if conversacion and conversacion.pk else None,
            datos={
                "herramientas": [c["herramienta"] for c in resultado.consultas],
                "modelo": settings.ASISTENTE_MODELO,
                "uso": resultado.uso,
                "completa": resultado.completo,
            },
            request=request,
        )
        return self._turno(request, conversacion, pregunta, None, turno)

    def _turno(self, request, conversacion, pregunta, error, turno=None):
        if not es_htmx(request):
            url = reverse("asistente:chat")
            return redirect(
                f"{url}?c={conversacion.pk}" if conversacion and conversacion.pk else url
            )
        turno = turno or {"pregunta": pregunta, "respuesta": error, "aviso": True}
        respuesta = responder(
            request,
            "asistente/_turno.html",
            {"turno": turno, "conversacion": conversacion, "oob": True},
        )
        if conversacion and conversacion.pk:
            respuesta["HX-Replace-Url"] = f"{reverse('asistente:chat')}?c={conversacion.pk}"
        return respuesta
