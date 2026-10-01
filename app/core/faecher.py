"""Fächer: Schloss öffnen und Zustand lesen – nur über die Treiber-Interfaces."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core import einstellungen
from app.core.protokoll import protokollieren
from app.db.models import Fach
from app.drivers.fehler import HardwareFehler
from app.drivers.lock import SchlossRegistry

log = logging.getLogger(__name__)

# Kerong verlangt ≥ 1000 ms; 1500 ms gibt Reserve bei Spannungsabfall.
IMPULS_MS_STANDARD = 1500


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
    except HardwareFehler as e:
        log.debug("Fach %d: %s", fach.nummer, e)
        return "gestoert"


async def schloss_status_alle(
    registry: SchlossRegistry, faecher: list[Fach]
) -> dict[int, str]:
    werte = await asyncio.gather(*(schloss_status(registry, f) for f in faecher))
    return {f.id: w for f, w in zip(faecher, werte)}


async def oeffnen(
    session: AsyncSession,
    registry: SchlossRegistry,
    fach: Fach,
    quelle: str,
    benutzer_id: int | None = None,
) -> bool:
    """Öffnet das Fach und protokolliert das Ergebnis. True bei Erfolg."""
    if fach.io_modul_id is None or fach.kanal is None:
        raise ValueError(f"Fach {fach.nummer} hat kein Schloss")
    dauer_ms = await einstellungen.lesen_int(
        session, "schloss.impuls_ms", IMPULS_MS_STANDARD
    )
    try:
        await registry.fuer_modul(fach.io_modul_id).open(fach.kanal, dauer_ms)
    except HardwareFehler as e:
        log.error("Fach %d öffnen fehlgeschlagen: %s", fach.nummer, e)
        protokollieren(
            session,
            "stoerung",
            fach_id=fach.id,
            benutzer_id=benutzer_id,
            quelle=quelle,
            fehler=str(e),
        )
        await session.commit()
        return False
    protokollieren(
        session,
        "fach_geoeffnet",
        fach_id=fach.id,
        benutzer_id=benutzer_id,
        quelle=quelle,
    )
    await session.commit()
    return True
