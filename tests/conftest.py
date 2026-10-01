"""Gemeinsame Fixtures: Hardware-Simulator im Testprozess auf freien Ports."""

import asyncio

import pytest

from hwsim.anlage import Anlage
from hwsim.leser import LeserSim
from hwsim.modbus import ModbusSimServer


@pytest.fixture
async def sim_modul():
    """Ein simuliertes Waveshare-Modul; liefert (anlage, modul, port)."""
    anlage = Anlage(ports=[0], min_impuls_ms=1000, tuer_zu_nach_s=0)
    modul = anlage.module[0]
    server = await ModbusSimServer(anlage, modul).starten("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async def ticker():
        while True:
            anlage.tick()
            await asyncio.sleep(0.02)

    task = asyncio.create_task(ticker())
    yield anlage, modul, port
    task.cancel()
    server.close()
    await server.wait_closed()


@pytest.fixture
async def sim_leser():
    leser = LeserSim()
    server = await leser.starten("127.0.0.1", 0)
    yield leser, server.sockets[0].getsockname()[1]
    server.close()
