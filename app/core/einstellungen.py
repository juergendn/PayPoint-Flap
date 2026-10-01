"""Einstellungen: Tabelle `einstellung` (Schlüssel/Wert als Text) und ihre
Beschreibung für das Webinterface.

Jede bearbeitbare Einstellung steht in DEFINITIONEN – mit Typ, Grenzen und
Standard. So prüft eine Stelle alle Eingaben, und Code liest nie einen Wert, den
das Formular nicht kennt.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Einstellung


@dataclass(frozen=True)
class Definition:
    schluessel: str
    titel: str
    gruppe: str
    typ: str = "int"  # int | text | email | passwort | auswahl
    standard: str = ""
    minimum: int | None = None
    maximum: int | None = None
    auswahl: tuple[str, ...] = ()
    hilfe: str = ""


DEFINITIONEN: tuple[Definition, ...] = (
    Definition(
        "schloss.impuls_ms",
        "Impulsdauer Schloss (ms)",
        "Automat",
        standard="1500",
        minimum=1000,
        maximum=5000,
        hilfe="Kerong KR-S70N braucht mindestens 1000 ms.",
    ),
    Definition(
        "display.timeout_s",
        "Display: Rückkehr zur Startseite nach (s)",
        "Automat",
        standard="60",
        minimum=15,
        maximum=600,
    ),
    Definition(
        "web.sitzung_min",
        "Webinterface: Abmeldung nach Inaktivität (min)",
        "Automat",
        standard="30",
        minimum=5,
        maximum=480,
    ),
    Definition(
        "tuer.max_offen_min",
        "Meldung, wenn eine Tür offen steht länger als (min)",
        "Automat",
        standard="10",
        minimum=1,
        maximum=240,
    ),
    Definition(
        "protokoll.tage",
        "Protokoll aufbewahren (Tage)",
        "Datenschutz",
        standard="60",
        minimum=1,
        maximum=365,
        hilfe="Mit dem Datenschutzbeauftragten des Kunden abstimmen.",
    ),
    Definition(
        "erinnerung.tage",
        "Erinnerung an Wäscheabteilung nach (Tagen)",
        "E-Mail",
        standard="5",
        minimum=1,
        maximum=60,
        hilfe="Nicht abgeholte Fächer werden dann gemeldet.",
    ),
    Definition(
        "mail.waesche",
        "Empfänger Wäscheabteilung",
        "E-Mail",
        typ="email",
    ),
    Definition("smtp.host", "SMTP-Server", "E-Mail", typ="text"),
    Definition(
        "smtp.port", "SMTP-Port", "E-Mail", standard="587", minimum=1, maximum=65535
    ),
    Definition(
        "smtp.sicherheit",
        "Verschlüsselung",
        "E-Mail",
        typ="auswahl",
        standard="starttls",
        auswahl=("starttls", "ssl", "keine"),
    ),
    Definition("smtp.benutzer", "SMTP-Benutzer", "E-Mail", typ="text"),
    Definition(
        "smtp.passwort",
        "SMTP-Passwort",
        "E-Mail",
        typ="passwort",
        hilfe="Leer lassen = unverändert.",
    ),
    Definition("smtp.absender", "Absender-Adresse", "E-Mail", typ="email"),
)
NACH_SCHLUESSEL = {d.schluessel: d for d in DEFINITIONEN}


async def lesen(session: AsyncSession, schluessel: str) -> str:
    eintrag = await session.get(Einstellung, schluessel)
    if eintrag is not None:
        return eintrag.wert
    d = NACH_SCHLUESSEL.get(schluessel)
    return d.standard if d else ""


async def lesen_int(session: AsyncSession, schluessel: str, standard: int) -> int:
    eintrag = await session.get(Einstellung, schluessel)
    if eintrag is None:
        return standard
    try:
        return int(eintrag.wert)
    except ValueError:
        return standard


async def alle(session: AsyncSession) -> dict[str, str]:
    """Aktuelle Werte aller definierten Einstellungen (mit Standard)."""
    gespeichert = {
        e.schluessel: e.wert
        for e in await session.scalars(
            select(Einstellung).where(Einstellung.schluessel.in_(NACH_SCHLUESSEL))
        )
    }
    return {
        d.schluessel: gespeichert.get(d.schluessel, d.standard) for d in DEFINITIONEN
    }


def pruefen(d: Definition, roh: str) -> tuple[str | None, str | None]:
    """(wert, fehler). wert None = nicht ändern (leeres Passwortfeld)."""
    wert = roh.strip()
    if d.typ == "passwort":
        return (wert or None), None
    if d.typ == "int":
        if not wert.lstrip("-").isdigit():
            return None, f"{d.titel}: ganze Zahl erwartet"
        zahl = int(wert)
        if d.minimum is not None and zahl < d.minimum:
            return None, f"{d.titel}: mindestens {d.minimum}"
        if d.maximum is not None and zahl > d.maximum:
            return None, f"{d.titel}: höchstens {d.maximum}"
        return str(zahl), None
    if d.typ == "email" and wert and ("@" not in wert or " " in wert):
        return None, f"{d.titel}: E-Mail-Adresse ungültig"
    if d.typ == "auswahl" and wert not in d.auswahl:
        return None, f"{d.titel}: ungültige Auswahl"
    if len(wert) > 500:
        return None, f"{d.titel}: zu lang"
    return wert, None


async def speichern(
    session: AsyncSession, formular: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Prüft und speichert alle Felder. Liefert (geänderte Schlüssel, Fehler).
    Bei Fehlern wird nichts gespeichert – halbe Konfigurationen sind schlimmer."""
    aktuell = await alle(session)
    neu: dict[str, str] = {}
    fehler: list[str] = []
    for d in DEFINITIONEN:
        if d.schluessel not in formular:
            continue
        wert, problem = pruefen(d, formular[d.schluessel])
        if problem:
            fehler.append(problem)
        elif wert is not None and wert != aktuell[d.schluessel]:
            neu[d.schluessel] = wert
    if fehler:
        return [], fehler
    for schluessel, wert in neu.items():
        eintrag = await session.get(Einstellung, schluessel)
        if eintrag is None:
            session.add(Einstellung(schluessel=schluessel, wert=wert))
        else:
            eintrag.wert = wert
    return list(neu), []
