"""RF-29 a RF-37 y RNF-12: monitoreo, indicadores, auditoría y reportes."""

from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria, RegistroInmutableError
from apps.envios import servicios
from apps.envios.estados import Estado
from apps.monitoreo import kpis

from .conftest import ITEMS, items_completos

pytestmark = pytest.mark.django_db


def test_auditoria_no_se_modifica_ni_elimina(envio):
    registro = RegistroAuditoria.objects.first()
    registro.descripcion = "alterado"
    with pytest.raises(RegistroInmutableError):
        registro.save()
    with pytest.raises(RegistroInmutableError):
        registro.delete()
    with pytest.raises(RegistroInmutableError):
        RegistroAuditoria.objects.all().update(descripcion="x")
    with pytest.raises(RegistroInmutableError):
        RegistroAuditoria.objects.all().delete()


def test_trigger_de_base_de_datos_bloquea_sql_directo(envio):
    tabla = RegistroAuditoria._meta.db_table
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"UPDATE {tabla} SET descripcion = 'x'")
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {tabla}")
    assert RegistroAuditoria.objects.count() == 1


def test_api_de_auditoria_es_solo_lectura(api_admin, envio):
    registro = RegistroAuditoria.objects.first()
    assert api_admin.get("/api/auditoria/").status_code == 200
    assert api_admin.delete(f"/api/auditoria/{registro.pk}/").status_code == 405
    assert api_admin.patch(f"/api/auditoria/{registro.pk}/", {}).status_code == 405


def test_mapa_en_transito(api_admin, envio_en_transito, conductor):
    servicios.registrar_ubicacion(
        conductor.usuario, envio_en_transito, latitud="1.22", longitud="-77.29"
    )
    datos = api_admin.get("/api/monitoreo/en-transito/").data
    assert len(datos) == 1
    assert datos[0]["posicion"] == [1.22, -77.29]
    assert len(datos[0]["ruta"]) == 2


def test_alerta_de_retraso(api_admin, envio):
    envio.programado_para = timezone.now() - timedelta(hours=2)
    envio.save()
    datos = api_admin.get("/api/monitoreo/alertas/").data
    assert [e["id"] for e in datos] == [envio.pk]
    assert datos[0]["esta_retrasado"] is True


def test_notificacion_de_novedades(api_admin, envio_en_transito, conductor):
    novedad = servicios.reportar_novedad(
        conductor.usuario, envio_en_transito, tipo="RETRASO", descripcion="Trancón"
    )
    assert len(api_admin.get("/api/monitoreo/novedades/").data) == 1
    api_admin.post(f"/api/monitoreo/novedades/{novedad.pk}/marcar-leida/")
    assert api_admin.get("/api/monitoreo/novedades/").data == []


def _entregar(envio, responsable, cuando, completo=True, con_llegada=True, conductor=None):
    if con_llegada:
        servicios.registrar_llegada(
            conductor.usuario, envio, latitud="1.2168", longitud="-77.2883", ocurrido_en=cuando
        )
    items = items_completos(envio)
    if not completo:
        items[0]["cantidad_recibida"] = "1"
    servicios.confirmar_recepcion(
        responsable.usuario,
        envio,
        items_recibidos=items,
        recibido_por_nombre="M",
        codigo_verificacion=envio.codigo_verificacion,
        latitud="1.2168",
        longitud="-77.2883",
        ocurrido_en=cuando,
    )


def test_indicadores_tabla_3(admin, institucion, conductor, responsable):
    ahora = timezone.now()
    envios = []
    for horas in (6, 5, 4, 3):
        e = servicios.crear_envio(
            admin,
            institucion=institucion,
            conductor=conductor,
            programado_para=ahora - timedelta(hours=horas),
            items=ITEMS,
        )
        servicios.registrar_salida(
            conductor.usuario,
            e,
            latitud="1.21",
            longitud="-77.28",
            ocurrido_en=ahora - timedelta(hours=horas, minutes=30),
        )
        envios.append(e)
    # 1) a tiempo y completo  2) tarde  3) a tiempo sin llegada registrada  4) con faltantes
    _entregar(
        envios[0],
        responsable,
        ahora - timedelta(hours=6) + timedelta(minutes=5),
        conductor=conductor,
    )
    _entregar(
        envios[1], responsable, ahora - timedelta(hours=5) + timedelta(hours=2), conductor=conductor
    )
    _entregar(
        envios[2], responsable, ahora - timedelta(hours=4), con_llegada=False, conductor=conductor
    )
    _entregar(
        envios[3], responsable, ahora - timedelta(hours=3), completo=False, conductor=conductor
    )
    # Un envío sin entregar no cuenta en el denominador.
    servicios.crear_envio(
        admin,
        institucion=institucion,
        conductor=conductor,
        programado_para=ahora + timedelta(hours=1),
        items=ITEMS,
    )

    i = kpis.calcular()
    assert i.total_envios == 5
    assert i.total_entregas == 4
    assert i.entregas_a_tiempo == 3 and i.porcentaje_a_tiempo == 75.0
    assert i.entregas_registro_completo == 3 and i.porcentaje_registro_completo == 75.0
    assert i.entregas_con_evidencia == 4 and i.porcentaje_con_evidencia == 100.0
    assert i.novedades == 1
    assert i.por_estado[Estado.CON_NOVEDAD.label] == 1


def test_evidencia_alterada_deja_de_ser_verificable(envio_en_transito, responsable):
    _entregar(envio_en_transito, responsable, timezone.now(), con_llegada=False)
    evidencia = envio_en_transito.evidencia
    assert evidencia.es_integra
    type(evidencia).objects.filter(pk=evidencia.pk).update(recibido_por_nombre="Otra persona")
    evidencia.refresh_from_db()
    assert not evidencia.es_integra
    assert kpis.calcular().entregas_con_evidencia == 0


def test_reportes_exportables(api_admin, envio_en_transito, responsable):
    _entregar(envio_en_transito, responsable, timezone.now(), con_llegada=False)
    r = api_admin.get("/api/reportes/")
    assert r.status_code == 200 and len(r.data["filas"]) == 1
    r = api_admin.get("/api/reportes/", {"formato": "pdf"})
    assert r["Content-Type"] == "application/pdf" and r.content.startswith(b"%PDF")
    r = api_admin.get(
        "/api/reportes/", {"formato": "xlsx", "institucion": envio_en_transito.institucion_id}
    )
    assert r.content[:2] == b"PK"


def test_reporte_filtra_por_conductor(api_admin, envio, otro_conductor):
    r = api_admin.get("/api/reportes/", {"conductor": otro_conductor.pk})
    assert r.data["filas"] == []


def test_reporte_con_fechas_invertidas(api_admin):
    r = api_admin.get("/api/reportes/", {"desde": "2026-12-01", "hasta": "2026-01-01"})
    assert r.status_code == 400
