"""Hintergrunddienst Leser: liest Chips, gibt sie an den Modus und verteilt die
Antwort live ans Display (SSE).

Was ein Chip bedeutet (Abholen, Anlernen, Menü …), entscheidet der Modus; der
Dienst kennt nur „Chip gesehen“ und entprellt.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.drivers.reader.base import ReaderDriver

log = logging.getLogger(__name__)

Meldung = dict[str, Any]


class LeserDienst:
    def __init__(
        self,
        leser: ReaderDriver,
        verarbeiten: Callable[[str], Awaitable[Meldung]],
        entprell_s: float = 2.0,
    ) -> None:
        self.leser = leser
        self._verarbeiten = verarbeiten
        # Der Leser meldet einen liegen gelassenen Chip mehrfach – das ist kein
        # neuer Vorgang (sonst öffnete ein Fach direkt ein zweites Mal).
        self._entprell_s = entprell_s
        self._letzter: tuple[str, float] = ("", 0.0)
        self._abonnenten: set[asyncio.Queue[Meldung]] = set()
        self._task: asyncio.Task | None = None

    def abonnieren(self) -> asyncio.Queue[Meldung]:
        q: asyncio.Queue[Meldung] = asyncio.Queue(maxsize=10)
        self._abonnenten.add(q)
        return q

    def abbestellen(self, q: asyncio.Queue[Meldung]) -> None:
        self._abonnenten.discard(q)

    def senden(self, meldung: Meldung) -> None:
        for q in list(self._abonnenten):
            try:
                q.put_nowait(meldung)
            except asyncio.QueueFull:
                pass  # langsamer Browser – verpasst eben eine Anzeige

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
                    await self.chip(kennung)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Der Leser ist das Herz des Automaten – nie endgültig aufgeben.
                log.exception("Leserdienst abgestürzt, Neustart in 2 s")
                await asyncio.sleep(2)

    async def chip(self, kennung: str) -> Meldung | None:
        jetzt = time.monotonic()
        if kennung == self._letzter[0] and jetzt - self._letzter[1] < self._entprell_s:
            return None
        self._letzter = (kennung, jetzt)
        try:
            meldung = await self._verarbeiten(kennung)
        except Exception:
            log.exception("Chip %s: Verarbeitung fehlgeschlagen", kennung)
            meldung = {"art": "fehler", "text": "Interner Fehler"}
        log.info("Chip %s → %s", kennung, meldung.get("art"))
        self.senden(meldung)
        return meldung
