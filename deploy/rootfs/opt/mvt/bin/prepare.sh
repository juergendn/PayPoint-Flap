#!/bin/sh
# Läuft einmal beim Start des Containers (inittab: sysinit), als root.

. /opt/mvt/bin/env.sh

chmod 1777 /tmp
mkdir -p /tmp/run "$PGSOCK"
chown postgres:postgres "$PGSOCK"

mkdir -p "$MVT_DATA_DIR/logs" "$MVT_DATA_DIR/ssh"
chown "$MVT_USER:$MVT_USER" "$MVT_DATA_DIR" "$MVT_DATA_DIR/logs"

# postgres muss durch /data/mvt hindurch auf pgdata und sein Log
chmod 0751 "$MVT_DATA_DIR"
touch "$PG_LOG" && chown postgres:postgres "$PG_LOG"
chown -R root:root "$MVT_DATA_DIR/ssh"
chmod 0700 "$MVT_DATA_DIR/ssh"

# Erster Start: leeren Cluster in /data anlegen. Danach nie wieder – die Daten
# überleben jedes Container-Update.
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGDATA"
    chown postgres:postgres "$PGDATA"
    chmod 0700 "$PGDATA"
    setpriv --reuid=postgres --regid=postgres --init-groups \
        "$PGBIN/initdb" -D "$PGDATA" -U postgres -E UTF8 --locale=C.UTF-8 \
        --auth-local=peer --auth-host=reject >> "$PG_LOG" 2>&1 \
        || echo "[prepare] initdb fehlgeschlagen, siehe $PG_LOG" >&2
elif [ "$(cat "$PGDATA/PG_VERSION")" != "$PG_MAJOR" ]; then
    echo "[prepare] FEHLER: Daten von PostgreSQL $(cat "$PGDATA/PG_VERSION"), Image hat $PG_MAJOR" >&2
fi

# DNS: icom OS setzt Adresse und Gateway von außen, aber keinen Nameserver. Der
# Router ist zugleich DNS-Relay (PayPoint-60, am Gerät geprüft).
# (Unter Docker --read-only ist resolv.conf eingehängt und nicht schreibbar.)
if [ -s "$MVT_DATA_DIR/resolv.conf" ]; then
    inhalt=$(cat "$MVT_DATA_DIR/resolv.conf")
else
    gateway=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
    inhalt=${gateway:+"nameserver $gateway"}
fi
if [ -n "$inhalt" ]; then
    { echo "$inhalt" > /etc/resolv.conf; } 2>/dev/null \
        || echo "[prepare] /etc/resolv.conf nicht schreibbar, bleibt wie sie ist" >&2
fi

# Gerätedateien legt icom OS an; dialout + 660, damit die App nicht root braucht.
for port in /devices/*_serial*; do
    [ -e "$port" ] || continue
    chgrp dialout "$port" 2>/dev/null && chmod 0660 "$port" 2>/dev/null \
        || echo "[prepare] Rechte von $port nicht änderbar" >&2
done
