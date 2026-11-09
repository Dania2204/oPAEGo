## Qué cambia

<!-- Resumen corto del cambio y por qué. -->

## Requerimientos relacionados

<!-- RF-xx / RNF-xx del documento del proyecto. -->

## Cómo se probó

- [ ] `pytest` en verde (cobertura ≥ 85 %)
- [ ] `ruff check . && ruff format --check .`
- [ ] `python manage.py makemigrations --check --dry-run`
- [ ] Probado en el panel web / con la app móvil (si aplica)

## Checklist

- [ ] La lógica de negocio pasa por `apps/envios/servicios.py` (no en vistas ni serializers)
- [ ] Sin secretos, `.env` ni datos personales (por ejemplo `bd/`) en el commit
- [ ] Matriz de trazabilidad del README actualizada si cambia un RF
