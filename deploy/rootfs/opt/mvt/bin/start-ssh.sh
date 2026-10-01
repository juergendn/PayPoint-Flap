#!/bin/sh
# SSH für Inbetriebnahme und Fehlersuche (inittab: respawn).
#
# Ob ein Paket SSH hat, entscheidet sich beim Bauen: build.sh nimmt
# deploy/authorized_keys mit, wenn die Datei existiert, und schreibt "+ssh" in die
# Beschreibung. Ohne Schlüssel kein Fernzugang; Passwörter nimmt dropbear nie an.

. /opt/mvt/bin/env.sh

keys=/opt/mvt/authorized_keys
hostkey="$MVT_DATA_DIR/ssh/dropbear_ed25519_host_key"

if [ ! -s "$keys" ]; then
    # Paket ohne SSH: schlafen, damit init nicht im Sekundentakt neu startet
    sleep 3600
    exit 0
fi

# Hostschlüssel in /data, damit er Updates überlebt
[ -f "$hostkey" ] || dropbearkey -t ed25519 -f "$hostkey" >/dev/null 2>&1

mkdir -p /root/.ssh
chmod 0700 /root/.ssh
cp "$keys" /root/.ssh/authorized_keys
chmod 0600 /root/.ssh/authorized_keys

exec dropbear -F -E -s -r "$hostkey" -p 22
