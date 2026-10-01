#!/bin/sh
# inittab: shutdown. busybox init lässt nach seinem SIGTERM nur eine Sekunde –
# zu wenig für einen sauberen Datenbank-Stopp. Erst die App (bis 10 s), dann
# PostgreSQL im Modus fast (Checkpoint, keine Wiederherstellung beim nächsten Start).

. /opt/mvt/bin/env.sh

if [ -f "$MVT_PIDFILE" ]; then
    pid=$(cat "$MVT_PIDFILE")
    if kill -TERM "$pid" 2>/dev/null; then
        n=0
        while kill -0 "$pid" 2>/dev/null && [ "$n" -lt 20 ]; do
            sleep 0.5
            n=$((n + 1))
        done
    fi
fi

setpriv --reuid=postgres --regid=postgres --init-groups \
    "$PGBIN/pg_ctl" stop -D "$PGDATA" -m fast -t 20 >> "$PG_LOG" 2>&1 || true
