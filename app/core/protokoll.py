"""Protokoll schreiben – zentrale Stelle, damit später Filter/Datenschutz greifen."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Ereignis

# Anzeige im Webinterface; unbekannte Arten erscheinen mit ihrem Schlüssel.
ARTEN = {
    "chip_gelesen": "Chip gelesen",
    "befuellung_begonnen": "Befüllung begonnen",
    "fach_befuellt": "Fach befüllt",
    "abholung": "Abholung",
    "fach_frei": "Fach frei",
    "zuweisung_storniert": "Zuweisung storniert",
    "fach_geoeffnet": "Fach manuell geöffnet",
    "fach_gesperrt": "Fach gesperrt",
    "fach_entsperrt": "Fach entsperrt",
    "stoerung": "Störung",
    "stoerung_quittiert": "Störung quittiert",
    "modul_stoerung": "IO-Modul ausgefallen",
    "modul_ok": "IO-Modul wieder erreichbar",
    "chip_angelernt": "Chip angelernt",
    "chip_angelegt": "Chip angelegt",
    "chip_zugeordnet": "Chip zugeordnet",
    "chip_geloest": "Chip gelöst",
    "chip_gesperrt": "Chip gesperrt",
    "chip_freigegeben": "Chip freigegeben",
    "chip_geloescht": "Chip gelöscht",
    "anmeldung": "Anmeldung",
    "anmeldung_fehlgeschlagen": "Anmeldung fehlgeschlagen",
    "benutzer_angelegt": "Benutzer angelegt",
    "benutzer_geaendert": "Benutzer geändert",
    "mitarbeiter_angelegt": "Mitarbeiter angelegt",
    "mitarbeiter_geaendert": "Mitarbeiter geändert",
    "mitarbeiter_import": "Mitarbeiter-Import",
    "einstellungen_geaendert": "Einstellungen geändert",
}


def protokollieren(
    session: AsyncSession,
    art: str,
    *,
    fach_id: int | None = None,
    chip_id: int | None = None,
    mitarbeiter_id: int | None = None,
    benutzer_id: int | None = None,
    **details: Any,
) -> Ereignis:
    """Fügt ein Ereignis zur Sitzung hinzu; Commit macht der Aufrufer, damit das
    Ereignis in derselben Transaktion wie die fachliche Änderung landet."""
    ereignis = Ereignis(
        automat_id=get_settings().automat_id,
        art=art,
        fach_id=fach_id,
        chip_id=chip_id,
        mitarbeiter_id=mitarbeiter_id,
        benutzer_id=benutzer_id,
        details=details or None,
    )
    session.add(ereignis)
    return ereignis
