# Gemeinsame Umgebung der Skripte in /opt/mvt/bin (wird per `.` eingelesen).

# /data überlebt den Re-Import des Containers, alles andere wird beim Update
# ersetzt. Deshalb liegt dort alles, was zur Laufzeit geschrieben wird.
MVT_DATA_DIR=/data/mvt
MVT_APP_DIR=/opt/mvt/app
MVT_USER=mvt
MVT_LOG="$MVT_DATA_DIR/logs/app.log"
PG_LOG="$MVT_DATA_DIR/logs/postgres.log"
MVT_PIDFILE=/tmp/run/mvt.pid

. /opt/mvt/pg_major
PGBIN=/usr/lib/postgresql/$PG_MAJOR/bin
PGDATA="$MVT_DATA_DIR/pgdata"
# Nur Unix-Socket, kein TCP: die Datenbank ist von außen nicht erreichbar.
PGSOCK=/tmp/run/postgresql

# init vererbt HOME=/; dorthin darf mvt nicht schreiben
export HOME=/tmp
export PYTHONUNBUFFERED=1
# .pyc liegen fertig im Image; zur Laufzeit schreibt niemand ins Image
export PYTHONDONTWRITEBYTECODE=1
export PATH=/opt/mvt/venv/bin:$PGBIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Peer-Authentifizierung über den Socket: Betriebssystem-Benutzer mvt = DB-Rolle mvt,
# kein Passwort, das irgendwo liegen müsste.
export MVT_DATABASE_URL="postgresql+asyncpg://mvt@/mvt?host=$PGSOCK"
export MVT_LESER_TREIBER=elatec_twn4
export MVT_LESER_URL=/devices/1_serial1
export MVT_LOG_LEVEL=INFO

# Gerätespezifische Abweichungen (anderer Leserport, Testaufbau …) überleben
# Updates in /data/mvt/env – Zeilen der Form MVT_…=wert.
if [ -f "$MVT_DATA_DIR/env" ]; then
    set -a
    . "$MVT_DATA_DIR/env"
    set +a
fi

