#!/bin/sh
# Startet die App (inittab: respawn). Endet die App, endet dieses Skript und
# init ruft es erneut auf.

. /opt/mvt/bin/env.sh

/opt/mvt/bin/rotate-log.sh einmal
log() { echo "[start] $(date '+%Y-%m-%d %H:%M:%S') $*" >> "$MVT_LOG"; }

# Auf die Datenbank warten (start-db.sh läuft parallel an).
n=0
until setpriv --reuid=postgres --regid=postgres --init-groups pg_isready -q -h "$PGSOCK" -U postgres; do
    n=$((n + 1))
    if [ "$n" -ge 60 ]; then
        log "Datenbank nach 60 s nicht bereit"
        sleep 3
        exit 1
    fi
    sleep 1
done

# Rolle und Datenbank beim ersten Start anlegen (idempotent).
psql_pg() { setpriv --reuid=postgres --regid=postgres --init-groups psql -h "$PGSOCK" -U postgres -qtA "$@"; }
psql_pg -c "SELECT 1 FROM pg_roles WHERE rolname='mvt'" | grep -q 1 \
    || psql_pg -c "CREATE ROLE mvt LOGIN" >> "$MVT_LOG" 2>&1
psql_pg -c "SELECT 1 FROM pg_database WHERE datname='mvt'" | grep -q 1 \
    || psql_pg -c "CREATE DATABASE mvt OWNER mvt" >> "$MVT_LOG" 2>&1

als_mvt="setpriv --reuid=$MVT_USER --regid=$MVT_USER --init-groups"
cd "$MVT_APP_DIR" || exit 1
version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
log "MVT-Klappenautomat $version startet"

# Migrationen und Grundeinrichtung bei jedem Start: nach einem Update zieht das
# Schema so von selbst nach.
if ! $als_mvt alembic upgrade head >> "$MVT_LOG" 2>&1 \
   || ! $als_mvt python -m app.seed >> "$MVT_LOG" 2>&1; then
    log "Migration/Grundeinrichtung fehlgeschlagen"
    sleep 10
    exit 1
fi

# Port 8000: als unprivilegierter Benutzer sind Ports < 1024 nicht erlaubt.
$als_mvt uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --timeout-graceful-shutdown 5 --no-server-header >> "$MVT_LOG" 2>&1 &
echo $! > "$MVT_PIDFILE"
wait $!
code=$?
rm -f "$MVT_PIDFILE"
log "App beendet (Code $code)"

# Bremse gegen eine Absturzschleife, die das Log vollschreibt.
sleep 3
