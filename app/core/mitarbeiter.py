"""Mitarbeiter: CSV-Import und Chip-Kennungen.

CSV-Format (bis die Personalsystem-Schnittstelle geklärt ist):
    personalnummer;name;email;abteilung
Kopfzeile Pflicht, Spaltenreihenfolge egal, Trennzeichen ; oder , (erkannt).
Kodierung UTF-8 (mit/ohne BOM) oder Windows-1252 – so speichert Excel.
Abgleich über die Personalnummer: neu → anlegen, vorhanden → aktualisieren.
"""

import csv
import io
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Mitarbeiter

MAX_ZEILEN = 5000
HEX = re.compile(r"^[0-9A-F]{4,64}$")

# Übliche Spaltennamen aus Personalsystemen auf unsere abbilden.
SPALTEN = {
    "personalnummer": "personalnummer",
    "personalnr": "personalnummer",
    "persnr": "personalnummer",
    "mitarbeiternummer": "personalnummer",
    "nr": "personalnummer",
    "name": "name",
    "email": "email",
    "e-mail": "email",
    "mail": "email",
    "abteilung": "abteilung",
}
PFLICHT = ("personalnummer", "name")


def kennung_normalisieren(text: str) -> str | None:
    """Chip-Kennung als Hex in Großbuchstaben, None wenn ungültig."""
    kennung = re.sub(r"[\s:-]", "", text).upper()
    return kennung if HEX.match(kennung) else None


@dataclass
class CsvZeile:
    personalnummer: str
    name: str
    email: str | None
    abteilung: str | None


@dataclass
class CsvErgebnis:
    zeilen: list[CsvZeile] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)


def _dekodieren(daten: bytes) -> str:
    try:
        return daten.decode("utf-8-sig")
    except UnicodeDecodeError:
        return daten.decode("cp1252")


def csv_lesen(daten: bytes) -> CsvErgebnis:
    ergebnis = CsvErgebnis()
    text = _dekodieren(daten)
    if not text.strip():
        ergebnis.fehler.append("Datei ist leer")
        return ergebnis
    kopf = text.splitlines()[0]
    trenner = ";" if kopf.count(";") >= kopf.count(",") else ","
    leser = csv.reader(io.StringIO(text), delimiter=trenner)

    spalten: dict[str, int] = {}
    for i, name in enumerate(next(leser)):
        ziel = SPALTEN.get(name.strip().lower())
        if ziel:
            spalten[ziel] = i
    fehlend = [p for p in PFLICHT if p not in spalten]
    if fehlend:
        ergebnis.fehler.append(
            f"Spalte(n) fehlen in der Kopfzeile: {', '.join(fehlend)}"
        )
        return ergebnis

    gesehen: set[str] = set()
    for nr, felder in enumerate(leser, start=2):
        if not any(f.strip() for f in felder):
            continue
        if nr > MAX_ZEILEN + 1:
            ergebnis.fehler.append(f"Mehr als {MAX_ZEILEN} Zeilen – Rest ignoriert")
            break

        def feld(name: str) -> str:
            i = spalten.get(name)
            return felder[i].strip() if i is not None and i < len(felder) else ""

        pnr, name = feld("personalnummer"), feld("name")
        if not pnr or not name:
            ergebnis.fehler.append(f"Zeile {nr}: Personalnummer oder Name fehlt")
            continue
        if len(pnr) > 30 or len(name) > 100:
            ergebnis.fehler.append(f"Zeile {nr}: Personalnummer/Name zu lang")
            continue
        if pnr in gesehen:
            ergebnis.fehler.append(f"Zeile {nr}: Personalnummer {pnr} doppelt")
            continue
        email = feld("email") or None
        if email and "@" not in email:
            ergebnis.fehler.append(f"Zeile {nr}: E-Mail „{email}“ ungültig")
            continue
        gesehen.add(pnr)
        ergebnis.zeilen.append(
            CsvZeile(pnr, name, email, feld("abteilung")[:100] or None)
        )
    return ergebnis


@dataclass
class ImportBilanz:
    neu: int = 0
    geaendert: int = 0
    unveraendert: int = 0
    deaktiviert: int = 0


async def csv_anwenden(
    session: AsyncSession, zeilen: list[CsvZeile], fehlende_deaktivieren: bool
) -> ImportBilanz:
    """Gleicht die Zeilen mit der DB ab. Commit macht der Aufrufer.

    Fehlende werden nur deaktiviert, nie gelöscht: Zuweisungen und Protokoll
    verweisen auf sie, und ein Fehler in der Exportdatei soll nichts zerstören.
    """
    bilanz = ImportBilanz()
    vorhanden = {
        m.personalnummer: m for m in await session.scalars(select(Mitarbeiter))
    }
    for z in zeilen:
        m = vorhanden.get(z.personalnummer)
        if m is None:
            session.add(
                Mitarbeiter(
                    personalnummer=z.personalnummer,
                    name=z.name,
                    email=z.email,
                    abteilung=z.abteilung,
                    aktiv=True,
                )
            )
            bilanz.neu += 1
            continue
        neu = (z.name, z.email, z.abteilung, True)
        if (m.name, m.email, m.abteilung, m.aktiv) == neu:
            bilanz.unveraendert += 1
        else:
            m.name, m.email, m.abteilung, m.aktiv = neu
            bilanz.geaendert += 1

    if fehlende_deaktivieren:
        in_datei = {z.personalnummer for z in zeilen}
        for pnr, m in vorhanden.items():
            if pnr not in in_datei and m.aktiv:
                m.aktiv = False
                bilanz.deaktiviert += 1
    return bilanz
