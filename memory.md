# memory.md – laufender Stand

Kurzprotokoll für die nächste Sitzung. Neueste Einträge oben.

## 01.10.2026 – Hardware-Entscheidungen

- **IO-Module: nur Waveshare.** romutec entfällt, Treiber `romutec_romod` gelöscht.
- **Leser TWN4 über RS-485** am Grundgerät (`/devices/1_serial1`), keine MRcard SI nötig.

## 01.10.2026 – Zielcontainer für icom OS (vorgezogen aus Meilenstein 9)

**Fertig**
- `deploy/`: LXC-Update-Paket nach dem am Gerät bestätigten Muster aus
  PayPoint-60/container (MANIFEST + `mvt-klappenautomat.tar.xz`, busybox init).
  Debian trixie, Python 3.12, **PostgreSQL 17 im Container** unter `/data/mvt/pgdata`.
- `deploy/boottest.sh`: Zielimage auf dem Mac mit `/sbin/init`, read-only rootfs,
  896 MB, gegen hwsim. Erststart, Absturz-Neustart, sauberer Stopp und
  Datenerhalt geprüft. ~95 MB RAM.
- `deploy/build.sh` → Paket 119 MB, Struktur geprüft. **Noch nicht am Gerät.**
- Seed ist jetzt Grundeinrichtung: Standard = echte IO-Adressen `.11–.13:502`, keine
  Testdaten; Entwicklung über `MVT_SEED_IO`/`MVT_SEED_TESTDATEN`.
- Entwicklung auf Postgres 17 und Debian trixie umgestellt (gleich wie Ziel).

**Entscheidungen**
- App auf Port 8000 (läuft als `mvt`, nicht root), Container eigene IP `.2`.
- DB nur per Unix-Socket mit Peer-Auth, kein Passwort, kein TCP.
- Gerätespezifisches in `/data/mvt/env` (überlebt Updates).
- Migration + Seed bei jedem Start.

**Erkenntnisse aus PayPoint-60** (siehe deploy/README.md)
- Grundgerät: nur `/devices/1_serial1`, RS-485 → **entschieden: TWN4 als RS-485-Variante** daran.
- Uhr = Router-Uhr; ohne NTP läuft sie nach.
- VPN-Zugriff auf die Container-App war dort nicht direkt möglich.

## 01.10.2026 – Meilenstein 1 + 2 (Gerüst, Simulator)

**Fertig**
- Docker Compose: `db` (PostgreSQL 16, sparsam), `hwsim` (Hardware-Simulator), `app`
  (FastAPI, Auto-Reload). Mac (Apple Silicon) = arm64 wie MOROS.neo.
- Datenmodell komplett laut CLAUDE.md, Migration `0001` inkl. Rollen/Rechte-Matrix
  und Standard-Einstellungen. Partielle Unique-Indizes: offene Zuweisung je
  Mitarbeiter **und** je Fach.
- Treiber: `waveshare_io8` (echt, Modbus TCP, Software-Watchdog), `elatec_twn4` (echt, pyserial
  `serial_for_url`), `simulator` (Lock + Reader im Prozess, für Tests).
- `hwsim`: eigener Modbus-TCP-Server (3 Module, Ports 5021–5023), Schloss-Physik
  (Impuls ≥ 1000 ms, Feder, Auto-Tür-zu), TWN4-Zeilenleser auf :7000, Web-UI :8081.
- Leserdienst mit Entprellung (2 s), Protokoll `chip_gelesen`, SSE `/events`.
- Display `/` (Live-Chipanzeige), Admin `/admin` (Fachübersicht, Testöffnung,
  Modul-/Leserstatus). **Noch ohne Login.**
- 10 Tests grün (`docker compose run --rm app pytest`).

**Entscheidungen**
- Simulator spricht echte Protokolle → in der Entwicklung laufen die *echten*
  Treiber. In-Prozess-Simulatoren nur für Unit-Tests.
- Modbus-Simulator selbst geschrieben statt pymodbus-Server (Datastore in 3.15
  abgekündigt; wir brauchen nur FC 1/2/5/15 und „Modul tot“).
- Impuls per Software (an → sleep → aus, `asyncio.shield`, 5 Abschaltversuche) +
  beim (Wieder-)Verbinden alle Ausgänge aus. Waveshare-Flash-Befehl (nicht
  standardkonformes FC05) am echten Modul prüfen.
- `io_modul.di_invertiert`: Öffner/Schließer des Schlossschalters noch offen.
- `LockDriver` hat zusätzlich `aclose()` (Verbindung beim Herunterfahren freigeben).
- Leser-Treiber über Umgebungsvariable (`MVT_LESER_*`), nicht DB – ein Leser je
  Automat, Port hängt am Gerät.
- Impulsdauer aus `einstellung.schloss.impuls_ms` (1500).
- Fach 1 (Steuerfach) ist nicht in der Tabelle `fach` – hat kein Schloss.
- Audiowide + htmx lokal unter `app/static/` (offline, kein CDN).
- Dev-Module teilen sich Host `hwsim` mit Ports 5021–5023; am Automaten eigene IPs
  `.11–.13` Port 502 – steht nur in der DB, Code unverändert.

**Nächste Schritte**
- Meilenstein 3: Login/Sitzungen, Rollen-/Rechteprüfung, Mitarbeiter + CSV-Import,
  Chips. Danach Admin-Seiten absichern.

