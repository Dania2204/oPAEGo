# PAEGo — Versión de presentación

Material para mostrar la plataforma a la **Secretaría de Educación Municipal de Pasto** sin
instalar nada.

## Plataforma en línea

La plataforma completa está publicada en **https://web-production-9a3cf.up.railway.app**. Ingrese con `admin@paego.local` y la
contraseña `Paego2026!`. A diferencia del HTML, ahí todo funciona y los cambios se guardan.

## Cómo abrirla

1. Abra `PAEGo-presentacion.html` con doble clic (Chrome, Edge o Firefox).
2. Pulse **Ingresar**: el correo y la contraseña ya vienen escritos.
3. Recorra los módulos con el menú lateral.

Se necesita conexión a internet solo para la tipografía, el mapa (OpenStreetMap) y los
gráficos. Sin internet, las pantallas se ven igual, pero el mapa muestra un aviso en lugar del
plano.

**Qué es y qué no es:** son las pantallas reales del panel web, con el diseño actual y los
datos de demostración. Es una vista de solo lectura: no está conectada al servidor y no guarda
cambios. Los botones que crean o modifican información muestran un aviso.

| Pantalla | Qué muestra |
|---|---|
| Hoy | Operación del día: lo que requiere atención, la lista de envíos y el mapa en tiempo real (RF-29, RF-30) |
| Envíos y detalle | Listado con filtros. El detalle tiene la ruta recorrida, la evidencia de entrega y el historial (RF-17, RF-27, RF-34, RF-35) |
| Novedades | Bandeja de incidencias reportadas (RF-31) |
| Programar envíos | Creación de los envíos de un día para varias instituciones |
| Catálogo | Instituciones, responsables, conductores y vehículos (RF-07 a RF-12) |
| Indicadores | Cifras de la Tabla 3 del documento (RF-32) |
| Reportes y auditoría | Exportación y registro inmutable (RF-33, RF-36, RF-37) |
| Usuarios | Administración de cuentas y roles (RF-04, RF-05) |

## Credenciales de ingreso a la plataforma

Funcionan en la plataforma en línea (https://web-production-9a3cf.up.railway.app) y en una instalación local después de cargar los datos de
demostración (`python manage.py seed_demo`, ver el README principal). Todos los usuarios tienen la misma
contraseña.

**Contraseña:** `Paego2026!`

| Rol | Correo | Dónde ingresa |
|---|---|---|
| Administrador | `admin@paego.local` | Panel web: https://web-production-9a3cf.up.railway.app |
| Conductor | `conductor1@paego.local` | App móvil (Flutter) / API |
| Conductor | `conductor2@paego.local` | App móvil (Flutter) / API |
| Conductor de prueba (mapa en vivo) | `conductor.prueba@paego.local` | Navegador del celular (comparte su ubicación) |
| Institución educativa | `institucion1@paego.local` | App móvil (Flutter) / API |
| Institución educativa | `institucion2@paego.local` | App móvil (Flutter) / API |

- La primera vez que un usuario ingresa debe aceptar la política de tratamiento de datos
  (Ley 1581 de 2012).
- Los conductores y las instituciones no tienen acceso al panel web. Si ingresan ahí, ven un
  aviso que los remite a la app móvil (mínimo privilegio, RF-06).
- Son credenciales **solo de demostración**. En un despliegue real se deben cambiar o eliminar.

## Regenerar este archivo

Si cambia el diseño, el archivo se vuelve a generar desde la aplicación en ejecución con
`scripts/presentacion/generar_presentacion.py`. Las instrucciones están al inicio de ese
script.
