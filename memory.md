# memory.md – laufender Stand

Kurzprotokoll für die nächste Sitzung. Neueste Einträge oben.

## 01.10.2026 – Meilenstein 7 (Mail + Hintergrunddienste)

**Fertig**
- `core/mail.py`: einreihen (gleiche Transaktion wie der Anlass) + Versand über
  smtplib im Thread (starttls/ssl/keine). EmailMessage gegen Header-Injection.
- `services/hintergrund.py`:
  - Maildienst alle 15 s; Wiederholung 1, 2, 4 … max. 60 min, nach 55 Versuchen
    (~2 Tage) `fehler`. Netzfehler → restliche Mails des Zyklus nicht probieren;
    SMTP-Fehler einer Mail (z. B. Empfänger abgelehnt) blockiert die anderen nicht.
    Ohne SMTP-Konfiguration bleibt alles in der Queue, ohne Versuch zu zählen.
  - Erinnerung (alle 10 min geprüft): Sammelmail an `mail.waesche` für Fächer
    belegt > `erinnerung.tage`; je Zuweisung einmal (`zuweisung.erinnert_am`).
  - Aufräumen täglich ab 03:00 Ortszeit (letzter Lauf in `einstellung`, übersteht
    Neustarts): Ereignisse und abgeschlossene Zuweisungen > `protokoll.tage`,
    gesendete/aufgegebene Mails > 30 Tage.
- Türüberwachung: Tür offen > `tuer.max_offen_min` (10) → einmal je Öffnung
  Protokoll + Mail an die Wäscheabteilung.
- Einstellungen: Testmail (sofort, zeigt echten SMTP-Fehler), letzte 10 Mails mit
  Status. Migration 0004 (`mail.naechster_versuch`, `zuweisung.erinnert_am`).
- Dev: Mailpit (http://localhost:8025), Seed trägt SMTP dafür ein.
- 58 Tests; live geprüft: Mail an Mitarbeiter, Testmail, Mailserver weg → Queue,
  Fach trotzdem belegt, Server zurück → zugestellt.

**Hinweis Tests:** `db`-Fixture setzt jetzt auch `einstellung` zurück.

**Nächste Schritte**
- Meilenstein 8: echte Treiber am Muster (Waveshare-Flash-Befehl, DI-Polarität,
  TWN4-Format/Baudrate an RS-485) – braucht Hardware.
- Meilenstein 9: Deployment am MRX/MOROS.neo (Paket hochladen, Netz, NTP, VPN).

## 01.10.2026 – Meilenstein 6 (Webinterface: Protokoll, Einstellungen)

**Fertig**
- Protokoll (`protokoll_lesen`): Filter Zeitraum (deutsche Kalendertage →
  UTC), Ereignisart, Fach, Mitarbeiter/Benutzer; 100 je Seite; CSV-Export für
  Excel (`;`, UTF-8-BOM, max. 50 000). Arten als Text in `core/protokoll.ARTEN`.
- Einstellungen (`einstellungen_verwalten`): `core/einstellungen.DEFINITIONEN`
  mit Typ/Grenzen/Standard; alles oder nichts speichern; Passwortfeld leer =
  unverändert, Wert nie angezeigt und nie im Protokoll. Gruppen Automat,
  Datenschutz, E-Mail (SMTP-Felder für Meilenstein 7 schon da). Systeminfo-Karte.
- Zeiten überall über Filter `ortszeit` (Europe/Berlin, `tzdata` als Paket),
  unabhängig von der Container-Zeitzone.
- 49 Tests.

**Hinweis**
- SMTP-Passwort liegt im Klartext in `einstellung` (muss zum Senden lesbar sein);
  Schutz = Datenbank nur per Unix-Socket im Container.

**Nächste Schritte**
- Meilenstein 7: Maildienst (Queue, Wiederholung, offline-fest), Erinnerung
  nach X Tagen an Wäscheabteilung, nächtliches Aufräumen (Protokoll > N Tage),
  Testmail-Knopf in den Einstellungen.

## 01.10.2026 – Meilenstein 5 (Display)

**Fertig**
- Display-Sitzung per Chip (`app/web/display/sitzung.py`): Chip eines Benutzers mit
  `fach_befuellen` → Token per SSE ans Panel, Kopf `X-Display-Token` bei jeder
  Aktion, Ablauf nach `display.timeout_s` (60 s) ohne Bedienung. Höchstens eine
  Sitzung; ein anderer Chip beendet sie (außer beim Anlernen).
- Bildschirme als HTMX-Fragmente (`templates/display/_*.html`): Start, Menü,
  Befüllen (Suche: Ziffern → Personalnummer-Anfang, sonst Name; Ziffernblock +
  QWERTZ mit Umlauten), Bestätigen (niedrigstes freies Fach), Warten auf Tür
  (Polling, 204 = weiter warten) → „belegt“ → „Nächstes Fach befüllen“,
  Fächerraster mit Öffnen/Sperren/Stornieren, Chip anlernen, Mein Fach.
- Chip-Antworten als Overlay (6 s). `static/js/display.js`: Token, SSE,
  Inaktivitäts-Timer mit Restanzeige, Bildschirmtastatur.
- Dev-Seed: `waesche` = Clara Wolf (Chip 04A1B2C3D6) → Menü am Display.
- 44 Tests; Durchlauf in Edge headless (1280×800) mit Screenshots, keine
  Browserfehler.

**Offen / später**
- Bestätigungen am Display nutzen noch `hx-confirm` (Browser-Dialog) – im Kiosk
  ggf. durch eigenen Dialog ersetzen.
- Auflösung WP10A am Gerät prüfen (angenommen 1280×800).

**Nächste Schritte**
- Meilenstein 6: Webinterface – Protokoll (Filter, 60 Tage), Einstellungen.

## 01.10.2026 – Meilenstein 4 (Modus bekleidung)

**Entschieden:** Fach ist erst frei, wenn die Tür nach der Abholung **wieder zu** ist.

**Fertig**
- Zustände `frei → befuellung → belegt → entnahme → frei` (+ `gestoert`, Flag
  `gesperrt`), Migration 0003. Übergänge nach `belegt`/`frei` nur per Türkontakt.
- `app/modes/bekleidung/ablauf.py` (`Bekleidung`): befuellen (Fach wählbar oder
  niedrigstes freies), stornieren (öffnet zum Ausräumen), abholen per Chip,
  oeffnen_manuell (kein Zustandswechsel), sperren, stoerung_quittieren, Anlernen
  (nächster unbekannter Chip, 60 s, optional direkt für einen Mitarbeiter).
  Alle Abläufe seriell über eine asyncio-Sperre.
- Öffnen prüft die Rückmeldung: Schloss nach Impuls noch zu → `gestoert`
  (mechanisch, manuell quittieren). Modul nicht erreichbar → nur Fehlermeldung, kein
  Zustandswechsel, Live-Anzeige „Störung“.
- `services/tuerkontakte.py`: Zyklus 1 s, Statuscache für die Übersicht,
  Protokoll nur bei Modul-Ausfall/-Rückkehr.
- Mail „Deine Kleidung liegt in Fach X“ beim Wechsel auf belegt (nur Queue).
- Chip-Reaktion: abholung | kein_fach | noch_nicht_bereit | fach_gesperrt | menue
  (Wäsche/Admin, mit eigenem Fach) | angelernt | unbekannt | nicht_zugeordnet |
  gesperrt. Display zeigt sie vorläufig als Text.
- Web: Fach-Detailseite mit allen Aktionen + letzte Ereignisse; Anlernen auf der
  Chip-Seite. 39 Tests, Live-Durchlauf mit hwsim, Migration im Container geprüft.

**Nächste Schritte**
- Meilenstein 5: Display (Kiosk) – Menü Wäsche nach Chip (Befüllen mit Suche/
  Ziffernblock, Stornieren, Anlernen, eigenes Fach), Timeout 60 s.

## 01.10.2026 – Meilenstein 3 (Login, Rollen, Mitarbeiter, Chips)

**Fertig**
- Login mit scrypt (stdlib), Sitzung als HMAC-signiertes Cookie (gleitend, Dauer aus
  `web.sitzung_min`), Schlüssel `web.geheimnis` in `einstellung` (überlebt Updates).
  Passwortwechsel macht alte Sitzungen ungültig. Fehlversuch: 1 s Bremse + Protokoll.
- Ersteinrichtung `/admin/einrichten` nur solange kein Benutzer existiert – **keine
  Standardpasswörter am Gerät**. Dev-Seed mit Testdaten: `admin/admin`, `waesche/waesche`.
- Rechteprüfung `Depends(recht("…"))`; Navigation zeigt nur Erlaubtes.
  Herkunftsprüfung (Origin/Referer) gegen CSRF + Cookie SameSite=strict.
- Mitarbeiter: Liste/Suche, Anlegen/Bearbeiten, CSV-Import mit Vorschau
  (`;`/`,`, UTF-8/Windows-1252, Spaltenaliasse, Abgleich über Personalnummer,
  Fehlende optional deaktivieren – nie löschen).
- Chips: anlegen, zuordnen/lösen, sperren, löschen; Filter „nicht zugeordnet“.
- Benutzer (Admin): Rolle, Mitarbeiter-Verknüpfung (für Rolle am Display),
  Passwort optional („nur Chip“); letzter aktiver Admin bleibt geschützt.
- Migration 0002: `ereignis.benutzer_id`. Alle Änderungen protokolliert.
- Inaktive Mitarbeiter gelten am Leser als unbekannt.
- 28 Tests (DB-Tests gegen `mvt_test`, frisch per Alembic migriert).
  Bootprobe: Update 0001 → 0002 auf bestehenden Daten im Container geprüft.

**Entscheidungen**
- Kein Sitzungsspeicher in der DB (Flash), dafür signierte Cookies.
- Templates bekommen `kopf`/`rechte` als einfache Werte, Integritätsfehler per
  Savepoint – sonst verfallen ORM-Objekte nach Rollback (MissingGreenlet).

**Nächste Schritte**
- Meilenstein 4: Modus bekleidung – Befüllen/Zuweisen, Abholen per Chip, Anlernen,
  Stornieren; Zustandsmaschine Fach (frei/belegt/gestört, gesperrt).
- Offener Punkt im Lastenheft: Fach frei bei Tür auf oder erst bei Tür zu?

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

