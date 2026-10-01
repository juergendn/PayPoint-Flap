# CLAUDE.md – MVT-Klappenautomat

Einstiegspunkt für die Arbeit an diesem Repo. Erst lesen, dann `wiki/` für Details,
`memory.md` für den laufenden Stand.

Stand: 01.10.2026 · Betreiber: MinervaTec eGbR, Aachen · Phase: Projektstart

---

## 1. Worum es geht

Klappenautomat mit 20 Fächern zur Ausgabe von Mitarbeiterbekleidung.

- **Fach 1** = Steuerfach (Router, Panel, Leser, Netzteil, IO-Module)
- **Fach 2–20** = 19 Ausgabefächer mit Motorschloss und Rückmeldung
- Gehäuse komplett aus **item-Profilen**

**Ablauf in einem Satz:** Die Wäscheabteilung legt Kleidung in ein freies Fach und weist
es am Display einem Mitarbeiter zu; der Mitarbeiter hält seinen Chip an den Leser, sein
Fach öffnet sich und ist danach wieder frei.

Eine Codebasis, **zwei Modi**:

| Modus | Status | Kurz |
|---|---|---|
| `bekleidung` | wird jetzt gebaut | Fach wird einem Mitarbeiter zugewiesen, nach Abholung leer |
| `werkzeug` | später | Entnahme/Rückgabe mit Ausleihfrist, Identifikation auch per Handy (BLE/NFC) |

Vollständige Anforderungen: Lastenheft (Claude Docs) → Kopie nach `wiki/lastenheft.md` legen.

---

## 2. Hardware

| Komponente | Rolle | Anbindung | Hersteller |
|---|---|---|---|
| INSYS **MOROS.neo-E.4G 1.0** | Rechner: Container mit App + DB, Router, VPN, 4G (baugleich MRX.neo aus PayPoint-60) | – | INSYS icom, Regensburg |
| tci **WP10A** | 10" Touch, Chromium-Kiosk, zeigt nur die Web-App | Ethernet | tci, Heuchelheim |
| ELATEC **TWN4 Palon Compact Panel** | RFID/NFC/BLE-Leser, LF+HF, Fronteinbau IP65 | **RS-485** an `/devices/1_serial1` (Grundgerät) | ELATEC, Puchheim |
| 3× Waveshare **Modbus POE ETH IO 8CH** | Schloss schalten, Rückmeldung lesen | Modbus TCP | Waveshare |
| Kerong **KR-S70N 24 V, Signalmodus 4** | Fachschloss mit Omron-Schalter, Nothebel | DO + DI | Kerong, Huizhou |
| Netzteil 24 V DC, ≥ 100 W | Versorgung | – | z. B. Phoenix Contact |

### IO-Module – Waveshare (entschieden, romutec entfällt)

3× Modbus POE ETH IO 8CH (Modbus TCP): Darlington-Ausgang, schaltet gegen Masse,
~1 V Abfall, eingebaute Impulsfunktion. ~100 € gesamt.

### Schloss KR-S70N (Signalmodus 4, 4-polig)

| Ader | Funktion | Anschluss Waveshare |
|---|---|---|
| rot | +24 V | +24 V über Sicherung |
| schwarz | Masse | DOx (schaltet gegen Masse) |
| blau | Schalter COM | DI COM |
| weiß | Schalter NO/NC | DIx |

- Entriegelt **einmal pro Spannungsimpuls**. Kerong: Impuls ≥ 1000 ms → wir nehmen **1500 ms**.
- Arbeitsspannung **23–25 V** → wegen ~1 V Abfall am Darlington Netzteil auf ~25 V trimmen, am Muster messen.
- Schloss verriegelt nur bei eingerastetem Haken → Schalter „verriegelt“ = Tür wirklich zu.
- Feder drückt Tür mit ~2 kg auf.

### Netzwerk (Automaten-LAN 192.168.10.0/24, isoliert)

| Adresse | Gerät |
|---|---|
| `.1` | MOROS.neo (Router, Gateway, DNS-Relay) |
| `.2` | LXC-Container: Web-App Port 8000 (eigene IP per Bridge) |
| `.11`–`.13` | IO-Module Waveshare #1–#3 |
| `.20` | Panel, Kiosk auf `http://192.168.10.2:8000` |

Fernzugriff nur über INSYS-VPN (icom Connectivity Suite). Modbus-Port 502 nie nach außen.

### Fachbelegung

| Fach | Modul | DO/DI |
|---|---|---|
| 2–9 | #1 | 1–8 |
| 10–17 | #2 | 1–8 |
| 18–20 | #3 | 1–3 |
| Reserve | #3 | 4–8 |

Belegung steht in der DB (`fach.io_modul`, `fach.kanal`), nie im Code.

---

## 3. Software

### Stack

- Python 3.12, **FastAPI**, **HTMX**, Jinja2-Templates
- **PostgreSQL** (sparsam konfiguriert, Flash schonen)
- `pymodbus` (TCP + RTU), `pyserial` für den Leser
- Läuft als **ein LXC-Container** auf dem MOROS.neo (icom OS, 1 GB RAM, ARM64):
  busybox init, App + PostgreSQL 17, Daten in `/data` → `deploy/README.md`
- Entwicklung lokal mit Docker Compose + Hardware-Simulator

### Schichten

```
Display (Kiosk) ─┐            ┌─ Webinterface (VPN)
                 ▼            ▼
           Web-App (FastAPI + HTMX)
                 │
        Modus: bekleidung | werkzeug
                 │
   Kern: Benutzer, Rollen, Chips, Fächer, Protokoll, Mail
                 │                         │
   Treiber: Schloss (IO)   Leser (TWN4)    PostgreSQL
```

**Regel:** Nur `drivers/` kennt Hardware. Modus und Kern sprechen ausschließlich gegen die
Interfaces.

### Treiber-Interfaces

```python
class LockDriver(Protocol):
    async def open(self, kanal: int, dauer_ms: int) -> None: ...
    async def is_locked(self, kanal: int) -> bool: ...
    async def health(self) -> bool: ...
    async def aclose(self) -> None: ...     # Verbindung beim Herunterfahren freigeben

class ReaderDriver(Protocol):
    async def chips(self) -> AsyncIterator[str]: ...   # liefert Kennung als Hex-String
    async def health(self) -> bool: ...
```

Implementierungen: `waveshare_io8`, `simulator` (Lock) ·
`elatec_twn4`, `simulator` (Reader). Auswahl über Tabelle `io_modul.treiber`
bzw. Umgebungsvariable `MVT_LESER_TREIBER`. Treiber melden Kommunikationsfehler
ausschließlich als `drivers.fehler.HardwareFehler`.

Entwicklung ohne Hardware: `hwsim/` (eigener Container) spricht echtes Modbus TCP und
das TWN4-Zeilenformat – dagegen laufen die echten Treiber. Details:
`wiki/testumgebung.html`.

### Repo-Struktur (Vorschlag)

```
mvt-klappenautomat/
├── CLAUDE.md
├── memory.md
├── wiki/                     # HTML mit Inline-SVG
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db/                   # Modelle, Migrationen (Alembic)
│   ├── core/                 # benutzer, rollen, chips, faecher, protokoll, mail
│   ├── modes/
│   │   ├── bekleidung/
│   │   └── werkzeug/         # leer, später
│   ├── drivers/
│   │   ├── lock/             # base.py, waveshare_io8.py, simulator.py
│   │   └── reader/           # base.py, elatec_twn4.py, simulator.py
│   ├── services/             # hintergrund: leser, tuerkontakte, mailqueue, aufraeumen
│   ├── web/
│   │   ├── display/          # Kiosk-Seiten
│   │   └── admin/            # Webinterface
│   └── templates/, static/
├── hwsim/                    # Hardware-Simulator (Modbus, Schlösser, Leser, UI)
├── tests/
├── deploy/                   # LXC-Paket für icom OS (build.sh, pack.py, boottest.sh, rootfs/)
└── docker-compose.yml        # lokale Entwicklung inkl. Simulator
```

### Datenmodell (Kurzfassung)

Jede Tabelle mit Gerätebezug trägt `automat_id` (spätere Zentralisierung).

| Tabelle | Wichtige Felder |
|---|---|
| `automat` | id, name, modus, standort |
| `io_modul` | automat_id, treiber, adresse, port, unit_id |
| `fach` | automat_id, nummer, io_modul_id, kanal, zustand, gesperrt |
| `mitarbeiter` | personalnummer, name, email, abteilung, aktiv |
| `chip` | kennung, technologie, mitarbeiter_id (NULL = nicht zugeordnet), aktiv |
| `benutzer` | login, passwort_hash, rolle, mitarbeiter_id |
| `rolle`, `recht` | Rechte als Einzelberechtigungen |
| `zuweisung` | fach_id, mitarbeiter_id, befuellt_von, befuellt_am, abgeholt_am, storniert |
| `ereignis` | zeitpunkt, automat_id, art, fach_id, chip_id, mitarbeiter_id, details |
| `mail` | empfaenger, betreff, text, status, versuche |
| `einstellung` | schluessel, wert |

Harte Regel in der DB: **höchstens eine offene Zuweisung pro Mitarbeiter** (partieller
Unique-Index).

### Rollen

| Recht | Admin | Wäsche | Mitarbeiter |
|---|---|---|---|
| Eigenes Fach abholen | ✓ | ✓ | ✓ |
| Befüllen/zuweisen, stornieren, Fach öffnen, sperren | ✓ | ✓ | – |
| Chips am Automaten anlernen, im Web verknüpfen | ✓ | ✓ | – |
| Protokoll einsehen | ✓ | ✓ | – |
| Mitarbeiter, Benutzer, Einstellungen | ✓ | – | – |

### Fachzustände (Modus bekleidung)

`frei` → (Befüllen + Tür zu bestätigt) → `belegt` → (Chip-Scan + Türkontakt meldet offen)
→ `frei`. Zusätzlich `gesperrt` (manuell) und `gestört` (Modul/Schloss antwortet nicht).

### Feste Vorgaben

- 250 Mitarbeiter, Auswahl am Display per Suche oder Mitarbeiternummer
- E-Mail an Mitarbeiter bei Befüllung, an Wäscheabteilung nach X Tagen (Einstellung)
- Protokoll als Ringspeicher **60 Tage**, nächtlicher Aufräumjob
- Display-Timeout 60 s, Web-Sitzung 30 min
- Schlossausgang wird **immer** nach der Impulsdauer abgeschaltet (Modul-Impulsfunktion
  oder Watchdog)
- Kein 4G → Automat arbeitet weiter, Mails warten in der Queue

---

## 4. Konventionen

- Kommentare, Docstrings, Commits und Doku **auf Deutsch**, Begründung („warum“) statt
  Nacherzählung
- Formatierung: **black** (Python), **prettier** (HTML/JS/CSS)
- Typannotationen überall, `async` für alle IO
- Keine Hardware-Adressen oder Kanäle im Code – alles aus DB/Konfiguration
- Offline-fähig: keine externen CDNs auf dem Display, alle Assets lokal ausliefern
- Doku nach Waypoint-Konvention: `CLAUDE.md` → `wiki/` → `memory.md`

---

## 5. Meilensteine

1. **Gerüst**: Repo, Docker Compose, FastAPI-Grundgerüst, DB-Schema + Alembic
2. **Simulator**: Lock- und Reader-Simulator, damit alles ohne Hardware läuft
3. **Kern**: Benutzer/Rollen/Login, Mitarbeiter inkl. CSV-Import, Chips
4. **Modus bekleidung**: Befüllen/Zuweisen, Abholen, Anlernen, Stornieren
5. **Display-UI**: Kiosk-Seiten, Ziffernblock, Live-Anzeige bei Chip-Scan (SSE)
6. **Webinterface**: Übersicht, Mitarbeiter, Chips, Protokoll, Einstellungen
7. **Mail + Hintergrunddienste**: Queue, Erinnerung, Aufräumen, Türkontakt-Überwachung
8. **Echte Treiber**: Waveshare, ELATEC TWN4 (RS-485)
9. **Deployment**: Container für icom OS, Test auf MOROS.neo
10. **Inbetriebnahme** am Muster mit echten Schlössern

---

## 6. Offene Punkte

- [ ] MOROS.neo-E.4G: Anzahl LAN-Ports
- [ ] TWN4 an RS-485: Baudrate, Busadresse/Protokoll am Muster prüfen
- [ ] KR-S70N: Schalter Öffner/Schließer, Haken A1/B1/C1, Spannung unter Last am Muster
- [ ] TWN4 Palon Compact Panel: Bestellnummer (Farbe/Anschluss), Ausgabeformat der Kennung
- [ ] Chip-Technologie beim Kunden (MIFARE, DESFire, 125 kHz, LEGIC?)
- [ ] Netzanbindung vor Ort (nur 4G oder auch Firmennetz)
- [ ] SMTP-Zugang, Absender, Empfängeradresse Wäscheabteilung, Frist X (Vorschlag 5 Tage)
- [ ] Datenschutz: Protokollfrist 60 Tage mit DSB des Kunden abstimmen
- [ ] Mitarbeiterdaten: CSV oder Schnittstelle zum Personalsystem
- [ ] Fach frei bei Tür **auf** oder erst bei Tür **wieder zu**?
- [ ] Uhrzeit: Router braucht NTP vor Inbetriebnahme (Container nutzt Router-Uhr)
- [ ] Webinterface per VPN erreichbar machen (Container-IP hinter dem Router, NAT?)
