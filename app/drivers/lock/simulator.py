"""Schloss-Simulator im Prozess – für Tests ohne Netzwerk.

Für die Entwicklung mit echtem Modbus-Verkehr gibt es zusätzlich `hwsim`
(eigener Container), gegen den der echte Waveshare-Treiber läuft.
"""

import asyncio

from app.drivers.fehler import HardwareFehler


class SimulatorLock:
    def __init__(self, kanaele: int = 8, **_: object) -> None:
        self.verriegelt = {k: True for k in range(1, kanaele + 1)}
        self.impulse: list[tuple[int, int]] = []
        self.online = True

    def _pruefe(self, kanal: int) -> None:
        if not self.online:
            raise HardwareFehler("Simulator offline")
        if kanal not in self.verriegelt:
            raise ValueError(f"Kanal {kanal} ungültig")

    async def open(self, kanal: int, dauer_ms: int) -> None:
        self._pruefe(kanal)
        self.impulse.append((kanal, dauer_ms))
        await asyncio.sleep(0)
        # Feder drückt die Tür auf → Schalter meldet nicht mehr verriegelt.
        self.verriegelt[kanal] = False

    def tuer_schliessen(self, kanal: int) -> None:
        self.verriegelt[kanal] = True

    async def is_locked(self, kanal: int) -> bool:
        self._pruefe(kanal)
        return self.verriegelt[kanal]

    async def health(self) -> bool:
        return self.online

    async def aclose(self) -> None:
        pass
