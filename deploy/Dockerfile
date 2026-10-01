# Wurzeldateisystem für den LXC-Container auf dem INSYS icom MRX/MOROS.neo (aarch64).
#
# Docker ist nur das Werkzeug, um ein arm64-Dateisystem reproduzierbar zu bauen.
# Auf dem Router läuft kein Docker: build.sh exportiert das Dateisystem und schnürt
# daraus ein icom-OS-Update-Paket. Gestartet wird /sbin/init (busybox) mit
# /etc/inittab – Format und Verhalten übernommen aus PayPoint-60/container, dort am
# Gerät bestätigt.
#
# Debian trixie + Python 3.12 (wie die Entwicklung) und PostgreSQL 17 aus Debian.
# Die PostgreSQL-Hauptversion ist an die Daten in /data gebunden: ein Wechsel
# braucht pg_upgrade bzw. Dump/Restore und ist ein eigenes Projekt.

FROM python:3.12-slim-trixie

ENV DEBIAN_FRONTEND=noninteractive
ARG PG_MAJOR=17

# Debian legt bei der Installation sonst einen Cluster unter /var/lib an – unsere
# Daten gehören nach /data (überlebt Updates).
RUN mkdir -p /etc/postgresql-common \
 && echo 'create_main_cluster = false' > /etc/postgresql-common/createcluster.conf \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-${PG_MAJOR} \
      busybox-static dropbear-bin \
      ca-certificates tzdata iproute2 \
 && rm -rf /var/lib/apt/lists/* \
 && busybox --list | grep -qx init \
 && test -x /usr/lib/postgresql/${PG_MAJOR}/bin/postgres

COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/mvt/venv \
 && /opt/mvt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
 && /opt/mvt/venv/bin/pip freeze > /opt/mvt/requirements.lock \
 && rm /tmp/requirements.txt

# Nur was zur Laufzeit gebraucht wird – kein hwsim, keine Tests.
COPY alembic.ini pyproject.toml /opt/mvt/app/
COPY app /opt/mvt/app/app
RUN /opt/mvt/venv/bin/python -m compileall -q /opt/mvt/app

COPY deploy/rootfs/ /

# mvt: unprivilegierter Benutzer für die App, dialout für den Leser.
# /devices, /data, /shared: Einhängepunkte, die icom OS erwartet.
# /usr/share/downloadable: erlaubt den Export des Containers aus dem Router.
RUN useradd --system --home-dir /opt/mvt --shell /usr/sbin/nologin --groups dialout mvt \
 && ln -sf /bin/busybox /sbin/init \
 && mkdir -p /devices /data /shared \
 && touch /usr/share/downloadable \
 && chmod 0755 /opt/mvt/bin/*.sh \
 && echo "PG_MAJOR=${PG_MAJOR}" > /opt/mvt/pg_major \
 && ln -snf /usr/share/zoneinfo/Europe/Berlin /etc/localtime \
 && echo 'Europe/Berlin' > /etc/timezone
