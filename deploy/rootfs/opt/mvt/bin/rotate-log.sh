#!/bin/sh
# Hält die Logs in /data klein:  rotate-log.sh einmal  |  rotate-log.sh wache
#
# Kopieren und leeren statt umbenennen: die Prozesse haben die Dateien mit >>
# (O_APPEND) offen und schreiben nach dem Leeren am neuen Ende weiter.
# Drei Generationen zu je 5 MB je Log (Muster aus PayPoint-60).

. /opt/mvt/bin/env.sh

MAX=5242880

rotieren() {
    for datei in "$MVT_LOG" "$PG_LOG"; do
        [ -f "$datei" ] || continue
        [ "$(stat -c %s "$datei")" -gt "$MAX" ] || continue
        [ -f "$datei.2" ] && mv -f "$datei.2" "$datei.3"
        [ -f "$datei.1" ] && mv -f "$datei.1" "$datei.2"
        cp -p "$datei" "$datei.1" && : > "$datei"
    done
}

case "${1:-einmal}" in
    wache)
        while :; do
            sleep 300
            rotieren
        done
        ;;
    *)
        rotieren
        ;;
esac
