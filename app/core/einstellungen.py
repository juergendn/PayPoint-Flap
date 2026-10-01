"""Zugriff auf die Tabelle `einstellung` (Schlüssel/Wert als Text)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Einstellung


async def lesen_int(session: AsyncSession, schluessel: str, standard: int) -> int:
    eintrag = await session.get(Einstellung, schluessel)
    if eintrag is None:
        return standard
    try:
        return int(eintrag.wert)
    except ValueError:
        return standard
