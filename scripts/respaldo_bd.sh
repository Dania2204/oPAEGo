#!/usr/bin/env sh
# RNF-14: copia de respaldo de la base de datos de PAEGo.
# Uso: sh scripts/respaldo_bd.sh   (programar con cron, p. ej. 0 2 * * *)
# Restaurar: docker exec -i pae-go-postgres pg_restore -U pae_user -d pae_go --clean < archivo.dump
set -eu
DESTINO="$(dirname "$0")/../respaldos"
mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/pae_go_$(date +%Y%m%d_%H%M%S).dump"
docker exec pae-go-postgres pg_dump -U pae_user -d pae_go -Fc > "$ARCHIVO"
echo "Respaldo creado: $ARCHIVO"
ls -1t "$DESTINO"/pae_go_*.dump | tail -n +31 | xargs -r rm --
