"""Protokoll schreiben – zentrale Stelle, damit später Filter/Datenschutz greifen."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Ereignis


def protokollieren(
    session: AsyncSession,
    art: str,
    *,
    fach_id: int | None = None,
    chip_id: int | None = None,
    mitarbeiter_id: int | None = None,
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
        details=details or None,
    )
    session.add(ereignis)
    return ereignis
