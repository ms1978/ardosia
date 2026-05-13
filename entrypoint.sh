#!/bin/sh
# Fix ownership: se PUID/PGID definidos, corre como esse utilizador
PUID=${PUID:-0}
PGID=${PGID:-0}

if [ "$PUID" != "0" ]; then
  chown -R "$PUID:$PGID" /data/caderno 2>/dev/null || true
  exec gosu "$PUID:$PGID" python3 ms78_api.py
else
  exec python3 ms78_api.py
fi
