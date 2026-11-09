"""El comando demo_mes genera un mes de operación realista y coherente."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.envios.estados import Estado
from apps.envios.models import EvidenciaEntrega, Ubicacion
from apps.monitoreo import kpis


@pytest.fixture
def demo(db):
    call_command("demo_mes", "--sin-ruteo", "--dias", "6", "--envios-dia", "2-3", "--semilla", "7")


def test_genera_envios_en_varios_estados(demo):
    from apps.envios.models import Envio

    estados = set(Envio.objects.values_list("estado", flat=True))
    # Hay operación cerrada y operación en curso hoy.
    assert Estado.ENTREGADO in estados or Estado.CON_NOVEDAD in estados
    assert Estado.EN_TRANSITO in estados
    assert Estado.ASIGNADO in estados


def test_hay_recorridos_y_evidencias_integras(demo):
    assert Ubicacion.objects.exists()
    evidencias = list(EvidenciaEntrega.objects.all())
    assert evidencias
    assert all(e.es_integra for e in evidencias)


def test_indicadores_con_datos(demo):
    hoy = timezone.localdate()
    total = kpis.calcular(hoy - timedelta(days=10), hoy)
    assert total.total_entregas > 0
    assert total.porcentaje_con_evidencia is not None


def test_datos_retrofechados(demo):
    from apps.envios.models import Envio

    # Algún envío quedó creado antes de hoy (no todo luce de hoy).
    limite = timezone.now() - timedelta(days=1)
    assert Envio.objects.filter(creado_en__lt=limite).exists()
    # Las ubicaciones históricas no se marcan como recibidas "ahora".
    antigua = Ubicacion.objects.order_by("ocurrido_en").first()
    assert antigua.recibido_en == antigua.ocurrido_en


def test_auditoria_no_toda_diferida(demo):
    # Gracias a hora_simulada, los eventos históricos no salen como «Sin conexión».
    assert RegistroAuditoria.objects.filter(diferido=False).exists()


def test_idempotente_sin_reiniciar(demo):
    from apps.envios.models import Envio

    antes = Envio.objects.count()
    call_command("demo_mes", "--sin-ruteo", "--dias", "6", "--envios-dia", "2-3", "--semilla", "7")
    assert Envio.objects.count() == antes
