#!/bin/sh
# PostgreSQL im Vordergrund (inittab: respawn).
#
# Einstellungen stehen hier statt in postgresql.conf: sie gehören zum Image und
# kommen mit jedem Update, die Datei in /data bliebe auf dem alten Stand.
# Sparsam für ~900 MB RAM und Flash: kleine Puffer, seltene Checkpoints.

. /opt/mvt/bin/env.sh

exec setpriv --reuid=postgres --regid=postgres --init-groups \
    "$PGBIN/postgres" -D "$PGDATA" \
    -c listen_addresses='' \
    -c unix_socket_directories="$PGSOCK" \
    -c shared_buffers=32MB \
    -c max_connections=20 \
    -c work_mem=2MB \
    -c maintenance_work_mem=16MB \
    -c checkpoint_timeout=15min \
    -c wal_writer_delay=1000ms \
    -c log_timezone=Europe/Berlin \
    -c timezone=Europe/Berlin \
    >> "$PG_LOG" 2>&1
