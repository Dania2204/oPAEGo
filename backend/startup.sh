#!/usr/bin/env bash
# Arranque en Azure App Service (Linux, Python). Lo ejecuta appCommandLine
# (infra/resources.bicep) dentro del entorno virtual que crea Oryx.
set -euo pipefail

python manage.py migrate --noinput
# Tabla de la caché compartida (CACHE_URL=dbcache://cache_paego): contadores
# del límite de intentos entre los workers de gunicorn.
python manage.py createcachetable
python manage.py collectstatic --noinput
if [ "${PAEGO_SEED_DEMO:-false}" = "true" ]; then
  python manage.py seed_demo # idempotente
fi

# App Service enruta al puerto 8000 por defecto.
exec gunicorn config.wsgi \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 --timeout 60 \
  --access-logfile -
