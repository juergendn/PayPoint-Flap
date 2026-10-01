"""Leser-Simulator im Prozess – Tests legen Kennungen per `vorhalten()` nach."""

import asyncio
from collections.abc import AsyncIterator


class SimulatorReader:
    def __init__(self, **_: object) -> None:
        self._warteschlange: asyncio.Queue[str] = asyncio.Queue()

    def vorhalten(self, kennung: str) -> None:
        self._warteschlange.put_nowait(kennung.upper())

    async def chips(self) -> AsyncIterator[str]:
        while True:
            yield await self._warteschlange.get()

    async def health(self) -> bool:
        return True
