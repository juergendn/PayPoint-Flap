# Container für den INSYS icom MRX/MOROS.neo

Der Klappenautomat läuft auf dem Router als **LXC-Container unter icom OS**. Docker
ist nur das Bauwerkzeug für ein arm64-Dateisystem, auf dem Router läuft kein Docker.

Format und Verhalten stammen aus **PayPoint-60/container** (baugleicher MRX3.neo-E,
dort am Gerät bestätigt, Stand 09/2026). Dort stehen auch die REST-API von icom OS
und das Rollout-Skript.

```
deploy/build.sh      ->  deploy/dist/mvt-klappenautomat_<version>.tar   (Update-Paket)
deploy/boottest.sh   ->  Zielimage auf dem Mac starten, wie icom OS es startet
```

## Was von PayPoint-60 übernommen ist

| Thema | Befund (PayPoint-60) | hier |
|---|---|---|
| Paket | unkomprimiertes tar, `MANIFEST` zuerst, dann `<name>.tar.xz` mit Präfix `rootfs/`, `FILETYPE=Container ARM64` | `pack.py` |
| Name | Innere Datei bleibt gleich → icom OS ersetzt den Container, **`/data` bleibt** | `mvt-klappenautomat.tar.xz` |
| Init | `/sbin/init` = busybox, `/etc/inittab`; kein systemd | `rootfs/etc/inittab` |
| Persistenz | nur `/data` überlebt Updates; `/tmp` tmpfs 100 MB | Datenbank + Logs unter `/data/mvt` |
| Netzwerk | eigene IP per Bridge, Adresse/Gateway setzt icom OS, Nameserver nicht | `prepare.sh` setzt DNS = Gateway |
| Seriell | `/devices/<Slot>_serial<n>`; Grundgerät nur `1_serial1` = **RS-485** | `MVT_LESER_URL=/devices/1_serial1` |
| Ressourcen | ~896 MB RAM für den Container | gemessen ~95 MB (App + PostgreSQL) |
| Rechte | unprivilegierter Container; App als eigener Benutzer, `dialout` | Benutzer `mvt` |

## Neu gegenüber PayPoint-60: PostgreSQL im Container

- Cluster in `/data/mvt/pgdata`, angelegt beim ersten Start (`prepare.sh`).
- Nur Unix-Socket (`listen_addresses=''`), Anmeldung per Peer: Benutzer `mvt` =
  Rolle `mvt`, kein Passwort.
- Einstellungen als `-c` in `start-db.sh`, damit sie mit dem Image kommen.
- `stop.sh` beendet erst die App, dann PostgreSQL mit `pg_ctl -m fast` (Checkpoint,
  keine Wiederherstellung beim nächsten Start). busybox init allein ließe nur 1 s.
- Bei jedem App-Start: `alembic upgrade head` + Grundeinrichtung (idempotent).
  Nach einem Update zieht das Schema dadurch von selbst nach.
- **Die PostgreSQL-Hauptversion (17) ist an `/data` gebunden.** Ein Wechsel braucht
  pg_upgrade oder Dump/Restore. `prepare.sh` meldet einen Versionskonflikt.

## Im Container

```
/opt/mvt/app          Code (gehört root, wird beim Update ersetzt)
/opt/mvt/venv         Python 3.12 + Abhängigkeiten
/opt/mvt/bin/         env.sh, prepare.sh, start-db.sh, start.sh, stop.sh, rotate-log.sh, start-ssh.sh
/data/mvt/
    env               gerätespezifische MVT_…=wert (optional, überlebt Updates)
    pgdata/           PostgreSQL
    logs/             app.log, postgres.log (je 3 × 5 MB)
    ssh/              Hostschlüssel (nur mit +ssh-Paket)
    resolv.conf       optional, sonst Nameserver = Gateway
```

App: `http://<Container-IP>:8000/`. Port 8000 statt 80, weil die App nicht als
root läuft.

## Inbetriebnahme

1. Router-Oberfläche → *Container* → *Container* → Paket hochladen.
2. Container einstellen: Bridge auf das Automaten-LAN (192.168.10.0/24), feste
   Adresse (Vorschlag `.2`), Gateway `.1`. Profil aktivieren.
3. Bei abweichendem Aufbau: `/data/mvt/env` anlegen (z. B. anderer Leserport).
4. Panel WP10A: Kiosk auf `http://192.168.10.2:8000/`.

## SSH

Wie PayPoint-60: Liegt `deploy/authorized_keys` (gitignored) beim Bauen da, kommt der
Schlüssel ins Image, dropbear läuft auf Port 22 (nur Schlüssel), das MANIFEST trägt
`+ssh`. Feldgeräte bekommen Pakete ohne `+ssh`.

## Bootprobe auf dem Mac

`deploy/boottest.sh` startet das Image mit `/sbin/init` als PID 1, schreibgeschütztem
Wurzeldateisystem (findet Schreibzugriffe ins Image), tmpfs `/tmp`, Volume `/data`,
896 MB RAM, gegen `hwsim` aus der Entwicklungsumgebung → `http://localhost:8002/`.
`deploy/boottest.sh reset` löscht `/data` (wie ein neuer Router).

Geprüft am 01.10.2026: Erststart mit initdb, Fach öffnen, Chip lesen, App-Absturz
(`kill -9`) → init startet neu, Stopp → PostgreSQL fährt sauber herunter, Neustart
→ Daten vorhanden, Seed läuft nicht doppelt.

## Offen

- Paket ist ~119 MB (PayPoint-60: 52 MB), vor allem PostgreSQL samt Perl.
  Verschlanken, wenn das Hochladen über 4G stört.
- Versionszählung und Rollout-Skript wie bei PayPoint-60 (`version.py`, `rollout.py`)
  bei Bedarf übernehmen.
- Uhrzeit: Der Container nutzt die Uhr des Routers. Ohne NTP läuft sie nach
  (PayPoint-60: 12 Tage). Protokoll und Erinnerungsfristen hängen daran.
- Fernzugriff per VPN: Bei PayPoint-60 war die App durch die VPN nicht direkt
  erreichbar (alle Container haben dieselbe LAN-Adresse). Das Webinterface braucht
  dafür eine Lösung (NAT/Portweiterleitung in der icom Connectivity Suite).
