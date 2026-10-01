"""Echter TWN4-Treiber (pyserial socket://) gegen den Leser-Simulator."""

import asyncio

from app.drivers.reader.elatec_twn4 import ElatecTwn4Serial
from app.drivers.reader.simulator import SimulatorReader


async def _naechster(chips, timeout=3.0):
    return await asyncio.wait_for(anext(chips), timeout)


async def test_twn4_liest_kennung(sim_leser):
    leser_sim, port = sim_leser
    treiber = ElatecTwn4Serial(f"socket://127.0.0.1:{port}", neuversuch_s=0.2)
    chips = treiber.chips()
    erster = asyncio.create_task(_naechster(chips))

    for _ in range(50):  # warten bis der Treiber verbunden ist
        if leser_sim.verbunden:
            break
        await asyncio.sleep(0.05)
    await leser_sim.vorhalten("04a1b2c3d4")

    assert await erster == "04A1B2C3D4"
    assert await treiber.health() is True
    await chips.aclose()


async def test_simulator_reader():
    leser = SimulatorReader()
    leser.vorhalten("abc123")
    assert await _naechster(leser.chips()) == "ABC123"
