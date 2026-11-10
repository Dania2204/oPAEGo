# Wireframes finales de PAEGo

Conjunto completo para el documento de tesis: las 17 vistas originales (`../wireframes/`) más el
**Supervisor PAE** (RF-39…42, propuestos), en web y en el celular. Todas las personas y documentos son
**ficticios** (Ley 1581): no hay datos reales del SIMAT.

## Web: panel del administrador (`web/`, 1440 px a 2×)

| Figura | Vista |
|---|---|
| 01–17 | Vistas originales (ingreso, Hoy, envíos, catálogo, control). Ver `../wireframes/README.md` |
| 18 | **Estudiantes PAE**: cobertura del día, avance por curso y lista del curso con método de entrega |
| 19 | Detalle de un estudiante **sin autorización**: formulario de autorización del acudiente |
| 20 | Detalle de un estudiante **autorizado**: rostro inscrito, revocar y entregas recientes |
| 21 | **Supervisores PAE**: lista por institución, desactivar |
| 22 | Registrar supervisor (correo, contraseña e institución) |

En la navegación aparecen dos entradas nuevas: "Estudiantes PAE" (Operación) y "Supervisores PAE" (Catálogo).

## Celular: app Flutter (`movil/`, 390 px a 2×)

| Figura | Vista |
|---|---|
| M01 | Supervisor · **Cursos** con el avance del día |
| M02 | Supervisor · **Curso 7° B** sin red: estado de cada estudiante y botón Reconocer |
| M03 | Acciones de un estudiante (inscribir rostro, entrega sin cámara, autorización, revocar) |
| M04 | **Entrega sin cámara** con motivo (alternativa manual obligatoria) |
| M05 | **Autorización del acudiente** antes de inscribir el rostro |
| M06 | **Inscribir rostro**: 5 fotos guiadas con prueba de vida (giro de cabeza) |
| M07 | **Reconocer**: coincidencia 1:N dentro del curso y confirmación del supervisor |
| M08 | **Historial** del supervisor, con lo que sigue en la cola sin conexión |
| M09 | Institución · **Estudiantes** atendidos hoy (solo lectura) |

## Regenerar

Las fuentes son HTML en `fuente/` (`web.html`, `movil.html`). Para exportar los PNG, desde
`oPAEGo/backend` con el `.venv` que trae Playwright:

```bash
python "../docs/wireframes finales/fuente/exportar.py"
```
