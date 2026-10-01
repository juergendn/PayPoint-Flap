"""Fächer: Schloss öffnen und Zustand lesen – nur über die Treiber-Interfaces."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core import einstellungen
from app.db.models import Fach
from app.drivers.fehler import HardwareFehler
from app.drivers.lock import SchlossRegistry

log = logging.getLogger(__name__)

# Anzeige der Fachzustände (Web und Display)
ZUSTAND_TEXT = {
    "frei": "frei",
    "befuellung": "wird befüllt",
    "belegt": "belegt",
    "entnahme": "wird geleert",
    "gestoert": "gestört",
}

# Kerong verlangt ≥ 1000 ms; 1500 ms gibt Reserve bei Spannungsabfall.
IMPULS_MS_STANDARD = 1500


class Oeffnungsfehler(Exception):
    """Fach ließ sich nicht öffnen. `grund`: 'kommunikation' (Modul antwortet
    nicht) oder 'mechanik' (Impuls kam an, Schloss meldet trotzdem zu)."""

    def __init__(self, grund: str, text: str) -> None:
        super().__init__(text)
        self.grund = grund


async def alle(session: AsyncSession) -> list[Fach]:
    ergebnis = await session.scalars(
        select(Fach)
        .where(Fach.automat_id == get_settings().automat_id)
        .options(selectinload(Fach.io_modul))
        .order_by(Fach.nummer)
    )
    return list(ergebnis)


async def schloss_status(registry: SchlossRegistry, fach: Fach) -> str:
    """'verriegelt' | 'offen' | 'gestoert' | 'ohne_io'"""
    if fach.io_modul_id is None or fach.kanal is None:
        return "ohne_io"
    try:
        treiber = registry.fuer_modul(fach.io_modul_id)
        return "verriegelt" if await treiber.is_locked(fach.kanal) else "offen"
    except (HardwareFehler, KeyError) as e:
        log.debug("Fach %d: %s", fach.nummer, e)
        return "gestoert"


async def schloss_status_alle(
    registry: SchlossRegistry, faecher: list[Fach]
) -> dict[int, str]:
    werte = await asyncio.gather(*(schloss_status(registry, f) for f in faecher))
    return {f.id: w for f, w in zip(faecher, werte)}


async def schloss_oeffnen(
    session: AsyncSession, registry: SchlossRegistry, fach: Fach
) -> None:
    """Impuls geben und prüfen, dass die Tür wirklich offen ist.

    Erst die Rückmeldung zählt: Ohne sie würde ein klemmendes Schloss als
    „geöffnet“ gelten, und der Türkontakt meldete gleich wieder „zu“ – das Fach
    wechselte dann ungesehen den Zustand.
    """
    if fach.io_modul_id is None or fach.kanal is None:
        raise Oeffnungsfehler("mechanik", f"Fach {fach.nummer} hat kein Schloss")
    dauer_ms = await einstellungen.lesen_int(
        session, "schloss.impuls_ms", IMPULS_MS_STANDARD
    )
    try:
        treiber = registry.fuer_modul(fach.io_modul_id)
        await treiber.open(fach.kanal, dauer_ms)
        noch_zu = await treiber.is_locked(fach.kanal)
    except (HardwareFehler, KeyError) as e:
        raise Oeffnungsfehler("kommunikation", f"Fach {fach.nummer}: {e}") from e
    if noch_zu:
        raise Oeffnungsfehler(
            "mechanik", f"Fach {fach.nummer}: Schloss meldet nach Impuls weiter zu"
        )
