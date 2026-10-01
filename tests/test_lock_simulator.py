import pytest

from app.drivers.fehler import HardwareFehler
from app.drivers.lock.simulator import SimulatorLock


async def test_oeffnen_und_schliessen():
    lock = SimulatorLock()
    await lock.open(2, 1500)
    assert await lock.is_locked(2) is False
    assert lock.impulse == [(2, 1500)]
    lock.tuer_schliessen(2)
    assert await lock.is_locked(2) is True


async def test_offline():
    lock = SimulatorLock()
    lock.online = False
    with pytest.raises(HardwareFehler):
        await lock.open(1, 1500)
