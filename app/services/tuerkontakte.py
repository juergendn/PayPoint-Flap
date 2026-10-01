"""Türüberwachung: liest alle Schlossschalter zyklisch.

- Schließt sich die Tür eines Fachs in `befuellung`/`entnahme`, meldet sie das
  dem Modus (→ belegt bzw. frei).
- Hält den letzten Schlossstatus im Speicher; die Admin-Übersicht liest daraus,
  statt selbst Modbus-Anfragen zu stellen.
- Schreibt nur bei Flanken ins Protokoll (Modul fällt aus/kommt wieder) – kein
  DB-Schreiben pro Zyklus (Flash).
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import faecher
from app.core.protokoll import protokollieren
from app.drivers.lock import SchlossRegistry
from app.modes.bekleidung.ablauf import Bekleidung

log = logging.getLogger(__name__)


class Tuerueberwachung:
    def __init__(
        self,
        registry: SchlossRegistry,
        session_factory: Callable[[], AsyncSession],
        modus: Bekleidung,
        intervall_s: float = 1.0,
    ) -> None:
        self._registry = registry
        self._session_factory = session_factory
        self._modus = modus
        self._intervall_s = intervall_s
        self.status: dict[int, str] = {}  # fach_id → verriegelt|offen|gestoert|ohne_io
        self._modul_ok: dict[int, bool] = {}
        self._task: asyncio.Task | None = None

    def starten(self) -> None:
        self._task = asyncio.create_task(self._lauf(), name="tuerueberwachung")

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
                await self.pruefen()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Türüberwachung: Fehler im Zyklus")
            await asyncio.sleep(self._intervall_s)

    async def pruefen(self) -> None:
        """Ein Zyklus (auch direkt aus Tests aufrufbar)."""
        async with self._session_factory() as session:
            liste = await faecher.alle(session)
        neu = await faecher.schloss_status_alle(self._registry, liste)

        for f in liste:
            if neu[f.id] == "verriegelt" and f.zustand in ("befuellung", "entnahme"):
                await self._modus.tuer_geschlossen(f.id)
        self.status = neu
        await self._modul_flanken(liste, neu)

    async def _modul_flanken(self, liste, neu: dict[int, str]) -> None:
        # Pro Modul statt pro Fach: ein ausgefallenes Modul ist ein Ereignis,
        # nicht acht.
        je_modul: dict[int, list[str]] = defaultdict(list)
        namen: dict[int, str] = {}
        for f in liste:
            if f.io_modul_id is not None:
                je_modul[f.io_modul_id].append(neu[f.id])
                namen[f.io_modul_id] = f.io_modul.name if f.io_modul else "?"
        flanken = []
        for modul_id, werte in je_modul.items():
            ok = any(w != "gestoert" for w in werte)
            alt = self._modul_ok.get(modul_id)
            if alt is not None and alt != ok:
                flanken.append((modul_id, ok))
            self._modul_ok[modul_id] = ok
        if not flanken:
            return
        async with self._session_factory() as session:
            for modul_id, ok in flanken:
                log.warning(
                    "IO-Modul %s %s",
                    namen[modul_id],
                    "wieder da" if ok else "AUSGEFALLEN",
                )
                protokollieren(
                    session,
                    "modul_ok" if ok else "modul_stoerung",
                    io_modul=namen[modul_id],
                )
            await session.commit()
