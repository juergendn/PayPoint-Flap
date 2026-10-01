"""Hintergrunddienst Leser: liest Chips, protokolliert und verteilt sie live (SSE).

Fachliche Reaktion (Fach öffnen, Anlernen …) hängt sich später als Modus-Logik
hier an; der Dienst selbst kennt nur „Chip gesehen“.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.protokoll import protokollieren
from app.db.models import Chip
from app.drivers.reader.base import ReaderDriver

log = logging.getLogger(__name__)


class LeserDienst:
    def __init__(
        self,
        leser: ReaderDriver,
        session_factory: Callable[[], AsyncSession],
        entprell_s: float = 2.0,
    ) -> None:
        self.leser = leser
        self._session_factory = session_factory
        # Der Leser meldet einen liegen gelassenen Chip mehrfach – das ist kein
        # neuer Vorgang.
        self._entprell_s = entprell_s
        self._letzter: tuple[str, float] = ("", 0.0)
        self._abonnenten: set[asyncio.Queue[dict[str, Any]]] = set()
        self._task: asyncio.Task | None = None

    def abonnieren(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10)
        self._abonnenten.add(q)
        return q

    def abbestellen(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._abonnenten.discard(q)

    def starten(self) -> None:
        self._task = asyncio.create_task(self._lauf(), name="leser")

    async def stoppen(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _lauf(self) -> None:
        while True:
            try:
                async for kennung in self.leser.chips():
                    await self._chip(kennung)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Der Leser ist das Herz des Automaten – nie endgültig aufgeben.
                log.exception("Leserdienst abgestürzt, Neustart in 2 s")
                await asyncio.sleep(2)

    async def _chip(self, kennung: str) -> None:
        jetzt = time.monotonic()
        if kennung == self._letzter[0] and jetzt - self._letzter[1] < self._entprell_s:
            return
        self._letzter = (kennung, jetzt)

        async with self._session_factory() as session:
            chip = await session.scalar(
                select(Chip)
                .where(Chip.kennung == kennung)
                .options(selectinload(Chip.mitarbeiter))
            )
            mitarbeiter = chip.mitarbeiter if chip and chip.aktiv else None
            protokollieren(
                session,
                "chip_gelesen",
                chip_id=chip.id if chip else None,
                mitarbeiter_id=mitarbeiter.id if mitarbeiter else None,
                kennung=kennung,
                bekannt=chip is not None,
            )
            await session.commit()

        meldung = {
            "kennung": kennung,
            "bekannt": chip is not None,
            "name": mitarbeiter.name if mitarbeiter else None,
        }
        log.info("Chip %s (%s)", kennung, meldung["name"] or "unbekannt")
        for q in list(self._abonnenten):
            try:
                q.put_nowait(meldung)
            except asyncio.QueueFull:
                pass  # langsamer Browser – verpasst eben eine Anzeige
