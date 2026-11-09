# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

PAEGo — plataforma **web** (Django 5 + DRF + SimpleJWT + PostgreSQL) para gestionar y monitorear
envíos del Programa de Alimentación Escolar (Pasto). Proyecto de grado. La fuente de verdad es el
documento de tesis `docs/CTG_29AGOSTO_DANIAURBINA (6).docx` (37 RF + 20 RNF; la copia `_v7_offline`
añade RF-38/RNF-21 sin conexión). El código debe seguir el documento: antes de una decisión de
arquitectura, revisarlo. La matriz RF → endpoint → prueba está en `README.md`.

- Este repo es **solo web**: API REST + panel del **administrador**. La app móvil (conductor e
  institución) es Flutter y vive en otro repo (`../trabajo_Final_Flutter`); no construir UIs web
  para conductor/institución. Única excepción aprobada: la pantalla temporal `/conductor/` que
  comparte GPS (modo de prueba del mapa en vivo).
- `prototipo-nextjs/` es un prototipo viejo, solo referencia; no se usa.

## Comandos (desde `backend/`)

```bash
docker compose up -d                 # (desde la raíz del repo) PostgreSQL 16 en el puerto 5434 del host
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py demo_mes            # ~1 mes de datos realistas (idempotente); --sin-ruteo sin internet
python manage.py seed_demo           # demo mínimo
python manage.py runserver           # settings por defecto: config.settings.dev

pytest                               # SQLite en memoria, no necesita Docker (config.settings.test)
pytest tests/test_envios.py::test_flujo_completo   # una sola prueba
pytest -k sincronizacion
ruff check . && ruff format --check .
python manage.py makemigrations --check --dry-run  # el CI falla si faltan migraciones
```

- Arranque rápido sin Docker: `DATABASE_URL=sqlite:///db.sqlite3` + `migrate` + `seed_demo`
  (con SQLite puede salir "database is locked" en POSTs concurrentes; es artefacto de SQLite).
- En esta máquina Postgres nativo ocupa 5432 y 5433 → el contenedor usa **5434**.
- `TEST_DATABASE_URL` hace correr pytest contra PostgreSQL. CI (`.github/workflows/ci.yml`,
  Python 3.13): ruff; makemigrations --check + pytest con `--cov-fail-under=85` sobre PostgreSQL;
  pip-audit `--strict` + `check --deploy` con settings de prod. También CodeQL, Dependabot y
  `cd.yml` (despliega a Railway tras CI verde en `main`; necesita el secreto `RAILWAY_TOKEN`).
- Credenciales demo: `admin@paego.local`, `conductor1..6@paego.local`, `institucion1..10@paego.local`,
  `conductor.prueba@paego.local`; contraseña `Paego2026!`.
- Despliegue: Railway, `railway up --service web` desde `backend/` (sin git). Los comandos de
  start/pre-deploy están configurados en el servicio de Railway, no en el repo. Prod:
  `config.settings.prod`, gunicorn + WhiteNoise.

## Arquitectura

- `config/settings/{base,dev,test,prod}.py`; variables con `django-environ`. Reglas de negocio
  configurables en `settings.PAEGO` (tolerancias, intervalos, umbral de "diferido").
- `config/api_urls.py` monta toda la API bajo `/api/` (namespace `api`); `config/urls.py` monta el
  panel web (cada app trae su `urls.py` con vistas de plantilla) y el service worker en `/sw.js`.
- Apps en `backend/apps/`, cada una con `api.py` (DRF) + `views.py` (panel) + `servicios.py`:
  `cuentas` (usuario propio `cuentas.Usuario`, roles `ADMINISTRADOR|CONDUCTOR|INSTITUCION`, JWT,
  permisos), `catalogo` (instituciones, conductores, vehículos, responsables, import SIMAT),
  `envios`, `monitoreo` (mapa, alertas, KPIs, posición en vivo, ruteo OSRM), `auditoria`
  (registro inmutable + reportes PDF/Excel), `sincronizacion` (lotes offline).
  `nutricion` (solo API: `POST /api/nutricion/asistente/` reenvía el chat de la app a Gemini con
  `GEMINI_API_KEY` del servidor, para que la clave no viaje en el APK; 503 sin clave, 502 si Gemini
  falla; cupo por usuario `LIMITE_NUTRICION`, clase `LimitePorUsuario` de `cuentas/limite.py`).
- **Una sola fuente de reglas:** API, panel y sincronización llaman a `apps/envios/servicios.py`
  (permisos por rol, transiciones, auditoría). No poner lógica de negocio en vistas/serializers.
  Las transiciones de estado (`ASIGNADO → EN_TRANSITO → ENTREGADO | CON_NOVEDAD`, `ASIGNADO →
  CANCELADO`) por rol están en `apps/envios/estados.py`.
- **Auth:** la app móvil usa `Authorization: Bearer`; el panel guarda el mismo JWT en cookies
  httpOnly (`paego_access`/`paego_refresh`) con CSRF. Access 10 min, refresh por inactividad 30 min.
  Límite de intentos por IP (`apps/cuentas/limite.py`, alcances `login`/`renovar`/`restablecer`,
  variables `LIMITE_*`) en la API (429) y en el login/restablecer del panel; contadores en la caché
  (`CACHE_URL`, por defecto memoria local por proceso). `tests/conftest.py` limpia la caché en cada prueba.
- **Offline (RF-38):** `POST /api/sincronizacion/lote/` aplica operaciones en orden cronológico,
  idempotentes por `uuid_cliente`, usando la hora real `ocurrido_en`. Despacho en
  `apps/sincronizacion/operaciones.py` (`OPERACIONES`); una operación puede referenciar un objeto
  creado offline por su `uuid_cliente`. Tipos disponibles: `GET /api/sincronizacion/configuracion/`.
  Indicadores e historial usan `ocurrido_en`, nunca la hora de llegada.
- **Auditoría inmutable:** modelo/queryset rechazan UPDATE/DELETE y hay trigger en BD
  (`auditoria/migrations/0003_registro_inmutable.py`) → los envíos no se pueden borrar una vez creados.
- Evidencia de entrega: código de 6 dígitos + foto opcional + ubicación + huella SHA-256.
- Contrato para Flutter: OpenAPI en `/api/schema/`, Swagger en `/api/docs/`.

## Frontend del panel

Plantillas Django + HTMX + Alpine.js, sin build. PWA con cola offline en IndexedDB
(`static/js/cola.js`). Diseño GOV.CO (Work Sans, `#3366CC`/`#004884`, tokens en
`static/css/tokens.css`). El usuario rechaza el look "hecho por IA": sin degradados, sin
mayúsculas con tracking, radios 4/6 px, sin tarjetas KPI genéricas; estados con texto + punto.

Mapas: MapLibre GL 5.6 + OpenFreeMap, estilo `estiloPaego` en `static/js/mapas.js`. Trampas:
- Crear el mapa solo después de tener el JSON del estilo (`PaegoMapas.listo()`).
- Toda animación de cámara con `freezeElevation: true` (si no, la cámara queda bajo el terreno 3D).
- No hacer `setData` de GeoJSON en cada frame; limitar a ~200 ms.
- No usar teselas CARTO raster (devuelven "API KEY REQUIRED" con HTTP 200).
- `SECURE_REFERRER_POLICY = strict-origin-when-cross-origin` es necesario para las teselas.
- Verificación visual: Playwright (instalado en `backend/.venv`) con `channel="chrome"`; para 3D
  usar `--enable-gpu --use-angle=d3d11` (swiftshader se cuelga).

## Reglas del usuario

- Git: commits en ramas de feature (no en `main`), Conventional Commits en español, autor Steven,
  nunca atribución a Claude (hook `commit-msg`). Preguntar antes de `git push` o abrir PR.
- Nunca commitear `bd/` (Anexo 6A de SIMAT con datos de estudiantes; está en `.gitignore`).
- Interfaz, código y mensajes en español.
