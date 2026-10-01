"""Schloss-Treiber: Auswahl über `io_modul.treiber`."""

from collections.abc import Callable

from app.db.models import IoModul
from app.drivers.lock.base import LockDriver
from app.drivers.lock.simulator import SimulatorLock
from app.drivers.lock.waveshare_io8 import WaveshareIo8

TREIBER: dict[str, Callable[..., LockDriver]] = {
    "waveshare_io8": WaveshareIo8,
    "simulator": SimulatorLock,
}


def erzeuge(modul: IoModul) -> LockDriver:
    try:
        fabrik = TREIBER[modul.treiber]
    except KeyError:
        raise ValueError(f"Unbekannter Schloss-Treiber '{modul.treiber}'") from None
    return fabrik(
        adresse=modul.adresse,
        port=modul.port,
        unit_id=modul.unit_id,
        di_invertiert=modul.di_invertiert,
    )


class SchlossRegistry:
    """Hält pro IO-Modul genau eine Treiberinstanz (und damit eine Verbindung)."""

    def __init__(self) -> None:
        self._treiber: dict[int, LockDriver] = {}

    def laden(self, module: list[IoModul]) -> None:
        for modul in module:
            self._treiber[modul.id] = erzeuge(modul)

    def fuer_modul(self, io_modul_id: int) -> LockDriver:
        return self._treiber[io_modul_id]

    async def schliessen(self) -> None:
        for treiber in self._treiber.values():
            await treiber.aclose()
        self._treiber.clear()
