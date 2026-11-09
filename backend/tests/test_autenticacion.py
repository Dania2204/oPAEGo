"""RF-01 a RF-06 y RNF-07 a RNF-09: autenticación JWT y control por rol."""

import re

import pytest
from django.conf import settings
from django.core import mail
from rest_framework.test import APIClient

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.cuentas.models import Rol, Usuario
from apps.cuentas.tokens import emitir_tokens

from .conftest import CLAVE, cliente_api, crear_usuario

pytestmark = pytest.mark.django_db


def test_inicio_sesion_api_devuelve_jwt_y_rol(conductor):
    r = APIClient().post(
        "/api/auth/token/", {"email": "CONDUCTOR@test.co", "password": CLAVE}, format="json"
    )
    assert r.status_code == 200
    assert {"access", "refresh"} <= set(r.data)
    assert r.data["usuario"]["rol"] == Rol.CONDUCTOR
    assert r.data["usuario"]["conductor_id"] == conductor.pk
    assert RegistroAuditoria.objects.filter(accion=Accion.INICIO_SESION).exists()


def test_credenciales_invalidas(conductor):
    r = APIClient().post(
        "/api/auth/token/", {"email": "conductor@test.co", "password": "mal"}, format="json"
    )
    assert r.status_code == 401


def test_usuario_desactivado_no_inicia_sesion(conductor):
    conductor.usuario.is_active = False
    conductor.usuario.save()
    r = APIClient().post(
        "/api/auth/token/", {"email": "conductor@test.co", "password": CLAVE}, format="json"
    )
    assert r.status_code == 401


def test_contrasena_guardada_con_hash(admin):
    assert admin.password != CLAVE
    assert admin.password.startswith(("pbkdf2_", "md5$", "argon2", "bcrypt"))


def test_sin_token_401():
    assert APIClient().get("/api/envios/").status_code == 401


def test_conductor_no_accede_a_funciones_de_administrador(api_conductor):
    assert api_conductor.get("/api/instituciones/").status_code == 403
    assert api_conductor.get("/api/usuarios/").status_code == 403
    assert api_conductor.get("/api/monitoreo/en-transito/").status_code == 403
    assert api_conductor.post("/api/envios/", {}, format="json").status_code == 403


def test_institucion_no_accede_a_auditoria(api_institucion):
    assert api_institucion.get("/api/auditoria/").status_code == 403
    assert api_institucion.get("/api/reportes/").status_code == 403


def test_cierre_sesion_revoca_refresh(conductor):
    tokens = emitir_tokens(conductor.usuario)
    cliente = cliente_api(conductor.usuario)
    assert (
        cliente.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code
        == 204
    )
    r = APIClient().post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert r.status_code == 401


def test_restablecer_contrasena(admin):
    r = APIClient().post("/api/auth/restablecer/", {"email": admin.email}, format="json")
    assert r.status_code == 202
    assert len(mail.outbox) == 1
    uid, token = re.search(r"/restablecer/([^/]+)/([^/\s]+)/", mail.outbox[0].body).groups()
    r = APIClient().post(
        "/api/auth/restablecer/confirmar/",
        {"uid": uid, "token": token, "nueva_password": "Nueva-Clave-2026"},
        format="json",
    )
    assert r.status_code == 204
    admin.refresh_from_db()
    assert admin.check_password("Nueva-Clave-2026")
    # El enlace es de un solo uso.
    r = APIClient().post(
        "/api/auth/restablecer/confirmar/",
        {"uid": uid, "token": token, "nueva_password": "Otra-Clave-2026"},
        format="json",
    )
    assert r.status_code == 400


def test_restablecer_no_revela_correos_inexistentes(db):
    r = APIClient().post("/api/auth/restablecer/", {"email": "nadie@x.co"}, format="json")
    assert r.status_code == 202
    assert len(mail.outbox) == 0


# ------------------------------------------------------------------ web
def test_login_web_administrador_pide_aceptar_tratamiento_datos(client, admin):
    r = client.post("/ingresar/", {"email": admin.email, "password": CLAVE})
    assert r.status_code == 200
    assert "tratamiento de datos" in r.content.decode()
    r = client.post("/ingresar/", {"email": admin.email, "password": CLAVE, "acepta_datos": "on"})
    assert r.status_code == 302 and r["Location"] == "/panel/"
    assert settings.JWT_COOKIE_ACCESS in r.cookies
    assert r.cookies[settings.JWT_COOKIE_ACCESS]["httponly"]
    admin.refresh_from_db()
    assert admin.acepto_tratamiento_datos_en is not None


def test_login_web_rechaza_institucion(client, responsable):
    r = client.post(
        "/ingresar/", {"email": responsable.usuario.email, "password": CLAVE, "acepta_datos": "on"}
    )
    assert r.status_code == 200
    assert "aplicación móvil" in r.content.decode()


def test_login_web_del_conductor_va_al_modo_en_vivo(client, conductor):
    # Modo de prueba del mapa en vivo: el conductor entra desde el celular.
    r = client.post(
        "/ingresar/?next=/panel/",
        {"email": conductor.usuario.email, "password": CLAVE, "acepta_datos": "on"},
    )
    assert r.status_code == 302 and r["Location"] == "/conductor/"
    assert client.get("/conductor/").status_code == 200
    assert client.get("/").url == "/conductor/"


def test_cookie_falsificada_no_da_acceso(client, admin):
    client.cookies[settings.JWT_COOKIE_ACCESS] = "token-inventado"
    client.cookies["pae_role"] = "ADMIN"
    r = client.get("/panel/")
    assert r.status_code == 302 and "/ingresar/" in r["Location"]


def test_panel_web_niega_a_conductor_con_token_valido(client, conductor):
    client.cookies[settings.JWT_COOKIE_ACCESS] = emitir_tokens(conductor.usuario)["access"]
    assert client.get("/panel/").status_code == 403


def test_access_vencido_se_renueva_con_refresh(client, admin):
    tokens = emitir_tokens(admin)
    client.cookies[settings.JWT_COOKIE_ACCESS] = "vencido"
    client.cookies[settings.JWT_COOKIE_REFRESH] = tokens["refresh"]
    r = client.get("/panel/")
    assert r.status_code == 200
    assert r.cookies[settings.JWT_COOKIE_ACCESS].value not in ("", "vencido")


def test_refresh_vencido_cierra_sesion_por_inactividad(client, admin, settings):
    from datetime import timedelta

    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(admin)
    refresh.set_exp(lifetime=-timedelta(minutes=1))
    client.cookies[settings.JWT_COOKIE_REFRESH] = str(refresh)
    r = client.get("/panel/")
    assert r.status_code == 302 and "/ingresar/" in r["Location"]


def test_cierre_sesion_web(web_admin):
    r = web_admin.post("/salir/")
    assert r.status_code == 302
    assert web_admin.get("/panel/").status_code == 302


def test_crud_usuario_administrador(api_admin):
    r = api_admin.post(
        "/api/usuarios/",
        {
            "email": "nuevo@test.co",
            "first_name": "Nuevo",
            "last_name": "Admin",
            "password": "Clave-Nueva-2026",
        },
        format="json",
    )
    assert r.status_code == 201
    nuevo = Usuario.objects.get(email="nuevo@test.co")
    assert nuevo.rol == Rol.ADMINISTRADOR
    r = api_admin.post(f"/api/usuarios/{nuevo.pk}/desactivar/")
    assert r.status_code == 200
    nuevo.refresh_from_db()
    assert not nuevo.is_active


def test_admin_no_se_desactiva_a_si_mismo(api_admin, admin):
    assert api_admin.post(f"/api/usuarios/{admin.pk}/desactivar/").status_code == 403


def test_desactivar_conductor_bloquea_su_token(api_admin, conductor):
    cliente = cliente_api(conductor.usuario)
    assert cliente.get("/api/envios/").status_code == 200
    api_admin.post(f"/api/conductores/{conductor.pk}/desactivar/")
    assert cliente.get("/api/envios/").status_code == 401


def test_crear_conductor_crea_usuario_con_rol(api_admin):
    r = api_admin.post(
        "/api/conductores/",
        {
            "email": "c@test.co",
            "first_name": "C",
            "last_name": "D",
            "password": "Clave-Cond-2026",
            "tipo_documento": "CC",
            "numero_documento": "999",
            "telefono": "3001",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert Usuario.objects.get(email="c@test.co").rol == Rol.CONDUCTOR


def test_crear_usuario_requiere_contrasena_segura(api_admin):
    r = api_admin.post(
        "/api/usuarios/",
        {"email": "x@test.co", "first_name": "X", "last_name": "Y", "password": "123"},
        format="json",
    )
    assert r.status_code == 400


def test_usuario_inactivo_fixture(db):
    u = crear_usuario("inactivo@test.co", Rol.ADMINISTRADOR, is_active=False)
    assert not u.is_active
