# PAEGo — Plataforma web

**Sistema integral de gestión y monitoreo del Programa de Alimentación Escolar (PAE).**
Proyecto de grado, Ingeniería de Software, Universidad Cooperativa de Colombia, sede Pasto (2026).
Autores: Dania Kathalina Urbina Portilla y Steven Alejandro Ortega Riascos.

Este repositorio contiene **solo la plataforma web**: un backend Django con la API REST y el
panel del administrador. La **aplicación móvil Flutter**, usada por el conductor y la
institución educativa, vive en **otro repositorio** y consume la API de este proyecto
(numeral 3.2.3 del documento).

```
oPAEGo/
├── backend/              Django 5 + Django REST Framework + JWT (este sistema)
│   ├── apps/
│   │   ├── cuentas/        usuarios, roles, JWT, restablecer contraseña      RF-01…06
│   │   ├── catalogo/       instituciones, conductores, vehículos, responsables RF-07…12
│   │   ├── envios/         envíos, ítems, estados, ubicaciones, novedades, evidencia RF-13…28
│   │   ├── monitoreo/      mapa en tiempo real, alertas, notificaciones, KPIs  RF-29…32
│   │   ├── auditoria/      registro inmutable, historial, reportes PDF/Excel   RF-33…37
│   │   ├── sincronizacion/ operaciones sin conexión idempotentes               RF-38
│   │   └── estudiantes/    supervisor PAE, autorización, rostro, entrega diaria RF-39…42
│   ├── templates/ static/  panel web del administrador (PWA, MapLibre)
│   ├── tests/              pruebas automáticas (pytest)
│   └── rendimiento/        pruebas de desempeño (locust) para ISO/IEC 25010
├── docs/                 documento del proyecto (.docx)
├── docs/presentacion/    HTML de presentación del panel y sus credenciales
├── scripts/              respaldo de la base de datos (RNF-14) y generador de la presentación
├── prototipo-nextjs/     prototipo visual inicial (solo referencia, no se usa)
└── docker-compose.yml    PostgreSQL 16
```

## Puesta en marcha

Requisitos: Python 3.12 o superior y Docker Desktop.

```bash
# 1. Base de datos PostgreSQL (puerto 5434 del host)
docker compose up -d

# 2. Entorno de Python
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # Linux/Mac: cp .env.example .env  (cambie DJANGO_SECRET_KEY)

# 3. Esquema y datos de demostración
python manage.py migrate
python manage.py demo_mes        # ~1 mes de operación realista (recomendado para probar/mostrar)
#   o bien, un demo mínimo:  python manage.py seed_demo

# 4. Servidor
python manage.py runserver
```

| URL | Para qué sirve |
|---|---|
| http://localhost:8000/ | Panel del administrador |
| http://localhost:8000/api/docs/ | Documentación de la API, Swagger (RNF-19) |
| http://localhost:8000/api/schema/ | Contrato OpenAPI que usa el equipo de la app Flutter |

### Credenciales de ingreso

`demo_mes` (o `seed_demo`) crea estos usuarios. Todos usan la contraseña **`Paego2026!`**.
Con `demo_mes` hay además `conductor1@paego.local` … `conductor6@paego.local` (con un mes de
recorridos y entregas) e `institucion1@paego.local` … `institucion10@paego.local` (10 colegios
reales de Pasto).

| Rol | Correo | Dónde ingresa |
|---|---|---|
| Administrador | `admin@paego.local` | Panel web: https://web-production-9a3cf.up.railway.app (o http://localhost:8000/ en local) |
| Conductor | `conductor1@paego.local` | App móvil / API |
| Conductor | `conductor2@paego.local` | App móvil / API |
| Conductor de prueba (mapa en vivo) | `conductor.prueba@paego.local` | Navegador del celular: la misma URL del panel |
| Institución educativa | `institucion1@paego.local` | App móvil / API |
| Institución educativa | `institucion2@paego.local` | App móvil / API |

El primer ingreso pide aceptar la política de tratamiento de datos (Ley 1581). Son credenciales
de demostración: en un despliegue real se deben cambiar.

### Plataforma en línea (Railway)

Desplegada en **https://web-production-9a3cf.up.railway.app** (proyecto `paego` en Railway: servicio `web` + PostgreSQL).

- Cada despliegue ejecuta `migrate` y **`demo_mes`** antes de arrancar, y luego `collectstatic` +
  `gunicorn`. Estos comandos están configurados en el servicio de Railway (no en el repo).
  `demo_mes` es idempotente: si ya hay envíos, no genera nada. Para **refrescar** el demo con un
  mes nuevo hasta la fecha, vacíe el volumen de PostgreSQL y vuelva a desplegar (la auditoría es
  inmutable, así que los envíos no se pueden borrar una vez creados).
- Variables del servicio: `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_SECRET_KEY`,
  `DATABASE_URL` (referencia a la base de PostgreSQL), `DJANGO_ALLOWED_HOSTS`,
  `DJANGO_CSRF_TRUSTED_ORIGINS`, `URL_PUBLICA` y `PORT=8080`.
- Los estáticos se sirven con WhiteNoise. `.railwayignore` evita subir `.env` y `.venv`.
- Para publicar cambios: `cd backend` y luego `railway up --service web`.
- Las fotos de evidencia se guardan en el disco del contenedor y se pierden en cada despliegue.
  Para una operación real se necesita un volumen o un almacenamiento de objetos.

### Versión de presentación (sin instalar nada)

`docs/presentacion/PAEGo-presentacion.html` contiene las pantallas reales del panel con datos de
demostración. Se abre con doble clic y sirve para mostrar el diseño a la Secretaría de Educación.
Vea `docs/presentacion/README.md`.

### Pruebas y estilo (RNF-18)

```bash
cd backend
pytest                    # SQLite en memoria (no necesita Docker)
ruff check . && ruff format --check .    # PEP 8
```

Para correr las pruebas contra PostgreSQL, defina `TEST_DATABASE_URL`. El CI de
`.github/workflows/ci.yml` lo hace en cada integración.

### Cobertura y raciones desde SIMAT (Anexo 6A)

El reporte oficial de matrícula del Ministerio (Anexo 6A de SIMAT, un `.xlsx` con una fila por
estudiante) se importa como **conteos agregados** para tres cosas: crear las **sedes reales** como
instituciones, sugerir la **cantidad de raciones** de un envío según los beneficiarios de la sede
(RF-14) y mostrar el **reporte de cobertura** del panel (menú «Cobertura»).

```bash
cd backend
python manage.py importar_simat <anexo6a.xlsx> --dane <CODIGO_DANE> --sedes sedes.csv --dry-run
python manage.py importar_simat <anexo6a.xlsx> --dane <CODIGO_DANE> --sedes sedes.csv
```

- **Privacidad (Ley 1581 de 2012).** El comando solo cuenta por sede, grado y jornada; **nunca
  almacena datos personales de los estudiantes** (nombre, documento, dirección, etc.). El modelo
  `catalogo.MatriculaSede` guarda únicamente totales. La entrega por estudiante (siguiente
  sección) usa otro comando, `importar_estudiantes`, que guarda solo la identidad mínima.
- `--dane` se repite para varias instituciones; `--dry-run` muestra el resumen sin escribir.
- El Anexo no trae el nombre de la institución ni sus coordenadas, así que se toman de un CSV
  aparte (`--sedes`) con las columnas `consecutivo_sede,nombre,sede,direccion,latitud,longitud`.
  Una sede sin coordenadas se omite con una advertencia.
- Es **idempotente**: reimportar reemplaza los conteos de cada sede y año sin duplicar nada
  (clave natural `consecutivo_sede`, el `CONS_SEDE` del Anexo).

### Supervisor PAE: entrega diaria por estudiante (RF-39…42, propuestos)

Un rol nuevo, **SUPERVISOR**, registra desde la app móvil qué estudiantes reciben el PAE cada día:
por curso, reconociendo la cara en el teléfono (sin red) o, siempre como alternativa, de forma
manual con motivo. El administrador lo ve en «Estudiantes PAE» (cobertura del día por curso y por
estudiante, autorizaciones, exportar a Excel) y crea los supervisores en «Supervisores PAE».

```bash
python manage.py importar_estudiantes <anexo6a.xlsx> --dane <CODIGO_DANE> --institucion "Normal Superior" --dry-run
```

- **Identidad mínima:** del Anexo 6A solo se guardan documento, nombres, apellidos, grado, grupo
  y jornada. Idempotente por `PER_ID`; quien ya no aparece queda inactivo y sin biometría.
- **Biometría (dato sensible, menores):** sin autorización vigente del acudiente no se inscribe
  un rostro. Se guardan plantillas numéricas (3–5 vectores) **cifradas con Fernet**
  (`BIOMETRIA_CLAVE`, Key Vault en Azure), nunca fotos. Revocar o dar de baja **borra** las
  plantillas y queda en la auditoría (que nunca guarda vectores).
- **Reglas:** una entrega por estudiante y día (restricción en la BD); FACIAL exige similitud ≥
  `UMBRAL_SIMILITUD_FACIAL` (0,80 por defecto, calibrar en el piloto); MANUAL exige motivo.
- La app trabaja sin red con la cola RF-38 (`estudiante.autorizar|inscribir|entregar|revocar`).

### Demo de un mes (`demo_mes`)

Genera una operación realista de ~un mes para probar y mostrar la plataforma: **10 colegios
reales de Pasto** con coordenadas reales, **6 conductores** con placas de Nariño, y envíos de ~20
días hábiles en distintos estados (entregados a tiempo, con novedad, tardíos, cancelados, y
actividad de hoy), con **recorridos GPS por calles**, novedades y evidencias íntegras. Es
determinista y pasa por los mismos servicios de dominio que la operación real.

```bash
cd backend
python manage.py demo_mes                      # 20 días, 6–10 envíos/día
python manage.py demo_mes --dias 30 --envios-dia 8-12 --semilla 7
python manage.py demo_mes --sin-ruteo          # recorridos sintéticos, sin internet
```

- **Recorridos por calles.** `apps/monitoreo/ruteo.py` pide la ruta a OSRM público (sin clave) y
  la guarda en `apps/monitoreo/data/rutas_demo.json` (caché versionada → offline y reproducible la
  próxima vez). Sin internet, cae a una ruta sintética. `--sin-ruteo` fuerza siempre la sintética.
- **Fidelidad temporal.** Los tiempos del evento (`ocurrido_en`) son históricos, así que
  indicadores, líneas de tiempo y mapas quedan correctos. Como la auditoría es **inmutable**, su
  `registrado_en` refleja el momento de la siembra; el cálculo de «Sin conexión» usa una hora
  simulada (`auditoria.servicios.hora_simulada`) para no marcar todo el historial como diferido.
- **Sin fotos de evidencia** (campo opcional; se perderían en cada despliegue). La evidencia es
  verificable igual (código + huella SHA-256).

## Diseño del panel web

- **Identidad GOV.CO:** el sistema de diseño del Gobierno de Colombia (Kit UI 9.2), con barra GOV.CO, tipografía **Work Sans** y azul institucional `#3366CC` / `#004884`. Los colores y tamaños están centralizados en `static/css/tokens.css`.
- **Interfaz operativa, no decorativa.** Se inspira en plataformas de despacho como Onfleet y Samsara:
  - La **excepción va primero**: la página **Hoy** abre con «Requiere atención», que reúne retrasados, novedades sin atender y envíos que salen pronto.
  - Al lado van el mapa y la lista del día. Se actualizan solos.
- **Panel lateral.** El detalle de un envío y los formularios de crear o editar se abren a la derecha sin salir de la lista (HTMX + Alpine.js, sin compilación de frontend). Cada panel tiene su propia URL, que se puede compartir o recargar.
- **Programar envíos.** Crea en un solo paso los envíos de un día para varias instituciones con el mismo menú. Se prellenan el último conductor y vehículo de cada institución.
- **Duplicar** un envío existente.
- **Atajos de teclado:** `n` nuevo envío, `p` programar, `/` buscar, `Esc` cerrar el panel, `?` ayuda.
- **Indicadores.** Cifras de la Tabla 3 con su tendencia semanal (una serie por gráfico, sin doble eje) y desglose por institución y por conductor.
- **Reglas de estilo:**
  - radio de 4/6 px;
  - estados de envío con texto y punto de color, nunca solo color;
  - sin degradados ni etiquetas en mayúsculas;
  - foco visible para teclado;
  - contraste AA;
  - diseño adaptable al celular.
- **Mapas:** MapLibre GL JS (mapa vectorial, el mismo tipo de motor que usan Uber o inDrive) con
  las teselas gratuitas de [OpenFreeMap](https://openfreemap.org). No necesita clave de API. El
  estilo parte de *liberty* y se retoca en `static/js/mapas.js` (`estiloPaego`) para que se vea como
  en las apps de transporte: fondo gris claro, calles blancas, avenidas en amarillo suave, parques
  verdes y sin íconos de comercios.
- **Vista 3D.** El mapa de **Hoy** y la pantalla del conductor abren en 3D, con un botón 2D/3D.
  La vista 3D incluye:
  - relieve real del terreno, con datos de elevación gratuitos de
    [Mapterhorn](https://mapterhorn.com), sin clave;
  - edificios con su altura, cámara inclinada y cielo en el horizonte.

  Los formularios abren en 2D para fijar puntos con precisión. Las animaciones de cámara usan
  `freezeElevation: true`; sin eso, MapLibre 5.6 deja la cámara bajo el terreno, porque Pasto
  está a unos 2.500 m de altura. `SECURE_REFERRER_POLICY` es `strict-origin-when-cross-origin`: solo se comparte el
  dominio. El mapa se redimensiona solo al abrir el panel lateral u ocultarlo, y muestra un aviso
  si no puede cargar. OpenFreeMap no ofrece garantía de disponibilidad; para una operación real se
  pueden alojar las teselas propias o contratar un proveedor.

### Mapa en vivo de conductores (modo de prueba)

Mientras llega la app Flutter, el conductor puede compartir su ubicación desde el navegador del
celular. El administrador lo ve moverse en el mapa de **Hoy**.

1. En el celular, abra la plataforma e ingrese con `conductor.prueba@paego.local` / `Paego2026!`.
   El navegador pide permiso de ubicación. Hace falta HTTPS, así que use la URL de Railway.
2. La pantalla del conductor envía la posición del GPS cada 3 s a `POST /api/monitoreo/mi-posicion/`
   mientras la sesión esté abierta. Se puede detener con un botón.
3. El panel consulta `GET /api/monitoreo/conductores-en-vivo/` cada 3 s. Muestra un auto que gira
   según el rumbo y se desliza de una posición a la siguiente, con una estela corta.
4. El conductor deja de verse al cerrar sesión, o si pasa 60 s sin enviar posición.

Esta posición en vivo (`monitoreo.PosicionEnVivo`) es independiente de las ubicaciones de cada
envío (RF‑21), que siguen igual. Cualquier conductor creado desde **Conductores** puede usar este
modo. Las instituciones siguen sin acceso a la web.

## Arquitectura

```
 Panel web (Django templates, PWA) ─┐
                                    ├─> API REST (DRF, JWT) ─> servicios de dominio ─> PostgreSQL (ORM)
 App móvil Flutter (otro repo) ─────┘            │
                                                 └─> registro de auditoría inmutable
```

- **Una sola fuente de reglas.** La API, el panel web y la sincronización sin conexión pasan
  por `apps/envios/servicios.py` y `apps/sincronizacion/operaciones.py`. Así, los permisos,
  las transiciones de estado y la auditoría se aplican siempre igual.
- **Autenticación JWT (RF-01, RNF-08).** La app móvil envía `Authorization: Bearer`. El panel
  web guarda el mismo JWT en una cookie httpOnly, con CSRF. El *access* dura 10 minutos y el
  *refresh* vence tras 30 minutos de inactividad (RF-02); ambos valores se configuran en `.env`.
- **Estados del envío (RF-18).** `ASIGNADO → EN_TRANSITO → ENTREGADO | CON_NOVEDAD`, y
  `ASIGNADO → CANCELADO`. La tabla de transiciones por rol está en
  `apps/envios/estados.py`.
- **Evidencia de entrega (RF-27, RNF-20).** Se compone de un código de verificación de 6
  dígitos (lo muestra el conductor y lo digita la institución), foto opcional, ubicación y una
  huella SHA-256 del contenido. Si la evidencia se altera, deja de verificarse.
- **Auditoría inmutable (RNF-12).** El modelo y el queryset rechazan UPDATE y DELETE, y además
  hay un *trigger* en PostgreSQL y SQLite (`auditoria/migrations/0003_registro_inmutable.py`).

### Funcionamiento sin conexión (RF-38 / RNF-21)

- Cada operación lleva un `uuid_cliente` generado en el dispositivo y la hora real del evento
  (`ocurrido_en`). El servidor es **idempotente**: si recibe dos veces la misma operación, la
  segunda devuelve `duplicado` y no crea nada nuevo.
- `POST /api/sincronizacion/lote/` aplica las operaciones en **orden cronológico** y valida
  cada una con las mismas reglas que en línea. Si una ya no es válida (por ejemplo, el envío fue
  cancelado mientras tanto), se devuelve `rechazado` con el motivo y queda auditada.
- Los indicadores y el historial usan `ocurrido_en`, la hora en que realmente pasó el evento.
  Una entrega que se sincroniza tarde no cuenta como entrega tardía. Los registros
  sincronizados tarde aparecen marcados como «Sin conexión».
- Un registro creado sin conexión todavía no tiene `id` en el servidor. Las operaciones
  siguientes pueden referenciarlo con el `uuid_cliente` de la operación que lo creó.
- **Panel web (PWA).** Un service worker guarda en caché la interfaz y las últimas páginas
  consultadas. Sin internet, los formularios se guardan en IndexedDB
  (`static/js/cola.js`). Al volver la conexión, la cola se envía sola y una barra informa
  cuántos cambios hay pendientes, cuántos se enviaron y cuántos fueron rechazados. Las
  contraseñas nunca se guardan en el equipo: crear usuarios requiere conexión.
- **App móvil.** Debe implementar la misma cola local y enviarla a `/api/sincronizacion/lote/`.
  Los tipos de operación disponibles se consultan en `/api/sincronizacion/configuracion/`.

## Matriz de trazabilidad

| RF | Requerimiento | Implementación (API / web) | Prueba |
|---|---|---|---|
| 01 | Iniciar sesión (JWT) | `POST /api/auth/token/` · `/ingresar/` | `test_autenticacion` |
| 02 | Cerrar sesión / expiración por inactividad | `/api/auth/logout/` · `/salir/` · refresh de 30 min | `test_cierre_sesion_*`, `test_refresh_vencido_*` |
| 03 | Restablecer contraseña | `/api/auth/restablecer/` · `/restablecer/` | `test_restablecer_contrasena` |
| 04–05 | Usuarios y roles | `/api/usuarios/` · `/usuarios/` (los roles de conductor e institución se asignan desde sus módulos) | `test_crud_usuario_administrador` |
| 06 | Mínimo privilegio | `cuentas/permisos.py`, queryset filtrado por rol | `test_*_no_accede_*`, `test_conductor_ajeno_*` |
| 07–08 | Instituciones | `/api/instituciones/` · `/instituciones/` (mapa para elegir coordenadas) | `test_registrar_y_desactivar_institucion` |
| 09–10 | Conductores | `/api/conductores/` · `/conductores/` | `test_crear_conductor_crea_usuario_con_rol` |
| 11 | Vehículos | `/api/vehiculos/` · `/vehiculos/` | `test_vehiculo_de_otro_conductor_rechazado` |
| 12 | Responsables de recepción | `/api/responsables/` · `/responsables/` | fixtures `responsable` |
| 13–15 | Crear envío, alimentos y asignación | `POST /api/envios/` · `/envios/nuevo/` | `test_flujo_completo`, `test_crear_envio_desde_la_web` |
| 16 | Reasignar, modificar o cancelar con motivo | `PUT /api/envios/{id}/`, `/reasignar/`, `/cancelar/` | `test_modificar_exige_motivo_*`, `test_reasignar_y_cancelar` |
| 17 | Listar y filtrar | `GET /api/envios/?fecha_desde&estado&institucion&conductor` · `/envios/` | `test_filtros_rf17` |
| 18 | Estados del envío | `envios/estados.py` | `test_estados.py` |
| 19 | Envíos del conductor | `GET /api/envios/` (filtrado por rol) | `test_flujo_completo` |
| 20 | Registrar salida | `POST /api/envios/{id}/salida/` | `test_flujo_completo` |
| 21 | Transmitir ubicación | `POST /api/envios/{id}/ubicaciones/` | `test_flujo_completo` |
| 22 | Registrar llegada | `POST /api/envios/{id}/llegada/` | `test_flujo_completo` |
| 23 | Novedades del trayecto con foto | `POST /api/envios/{id}/novedades/` (multipart o base64) | `test_novedad_del_conductor_*` |
| 24 | Envíos hacia la institución | `GET /api/envios/` (filtrado por institución) | `test_flujo_completo` |
| 25–27 | Verificar cantidades, confirmar, evidencia | `POST /api/envios/{id}/confirmar/` | `test_flujo_completo`, `test_codigo_*` |
| 28 | Novedades en la recepción | diferencias en `confirmar` y `novedades` | `test_recepcion_con_faltantes_*`, `test_hallazgo_*` |
| 29 | Mapa en tiempo real | `/api/monitoreo/en-transito/` · `/monitoreo/` | `test_mapa_en_transito` |
| 30 | Alertas de retraso | `/api/monitoreo/alertas/` · panel | `test_alerta_de_retraso` |
| 31 | Notificar novedades | `/api/monitoreo/novedades/` · `/novedades/` · contador en el menú | `test_notificacion_de_novedades` |
| 32 | Panel de indicadores (Tabla 3) | `/api/monitoreo/indicadores/` · `/panel/` | `test_indicadores_tabla_3` |
| 33 | Auditoría automática | `auditoria/servicios.registrar` · `/auditoria/` | `test_auditoria_*`, `test_trigger_*` |
| 34 | Historial (línea de tiempo) | `/api/envios/{id}/historial/` · detalle del envío | `test_flujo_completo` |
| 35 | Ruta recorrida | `GET /api/envios/{id}/ubicaciones/` · mapa en el detalle | `test_flujo_completo` |
| 36–37 | Reportes y exportación PDF/Excel | `/api/reportes/?formato=pdf\|xlsx` · `/reportes/` | `test_reportes_exportables` |
| 38 | Operación sin conexión y sincronización | `/api/sincronizacion/lote/` · PWA | `test_sincronizacion.py` |
| 39* | Rol supervisor PAE por institución | `Rol.SUPERVISOR`, `estudiantes.Supervisor` · `/supervisores/` | `test_admin_crea_un_supervisor`, `test_supervisor_lista_solo_su_institucion` |
| 40* | Autorización del acudiente e inscripción facial | `estudiante.autorizar`, `estudiante.inscribir` (lote) · detalle en `/estudiantes/` | `test_flujo_completo_por_el_lote`, `test_inscripcion_sin_autorizacion_se_rechaza` |
| 41* | Entrega diaria por estudiante (facial o manual) | `estudiante.entregar` (lote) · `GET /api/estudiantes/plantillas/` | `test_segunda_entrega_del_dia_se_rechaza`, `test_estudiantes.py` |
| 42* | Cobertura por estudiante y exportación | `GET /api/estudiantes/cursos/`, `/historial/` · `/estudiantes/`, `/estudiantes/exportar/` | `test_cobertura_y_lista_del_curso`, `test_exportar_excel` |

\* Requisitos propuestos para integrar en el documento de tesis.

| RNF | Cómo se cumple |
|---|---|
| 01–03 | `rendimiento/locustfile.py`; los valores objetivo se definen en el documento |
| 05–06 | Interfaz en español; los errores de la API se muestran campo por campo |
| 07 | Permisos por rol en la API y en la web |
| 08 | JWT con expiración (SimpleJWT) y lista negra al cerrar sesión |
| 09 | Contraseñas con hash PBKDF2 y validadores de contraseña |
| 10 | `config/settings/prod.py`: HTTPS obligatorio, HSTS y cookies `Secure` |
| 11 | Aceptación de la política de datos (Ley 1581) registrada en el primer ingreso |
| 12 | Auditoría inmutable: aplicación + *trigger* en la base de datos |
| 14 | `scripts/respaldo_bd.ps1` / `.sh` (`pg_dump`) |
| 17 | ORM de Django; el motor se cambia con `DATABASE_URL` |
| 18 | ruff (PEP 8) y pytest en GitHub Actions |
| 19 | OpenAPI/Swagger en `/api/docs/` |
| 20 | Evidencia con código de verificación y huella SHA-256 |
| 21 | Sincronización idempotente por `uuid_cliente` |
| 22* | Biometría de menores: autorización previa, plantillas cifradas, sin fotos, borrado al revocar y alternativa manual |
