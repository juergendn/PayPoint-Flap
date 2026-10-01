"""Echter Waveshare-Treiber gegen den Modbus-Simulator."""

import asyncio

import pytest

from app.drivers.fehler import HardwareFehler
from app.drivers.lock.waveshare_io8 import WaveshareIo8


async def test_impuls_entriegelt_und_schaltet_ab(sim_modul):
    anlage, modul, port = sim_modul
    treiber = WaveshareIo8("127.0.0.1", port=port)

    assert await treiber.is_locked(3) is True
    await treiber.open(3, 1200)

    assert modul.schloesser[2].ausgang is False, "Ausgang muss nach Impuls aus sein"
    assert await treiber.is_locked(3) is False
    assert all(s.verriegelt for i, s in enumerate(modul.schloesser) if i != 2)
    await treiber.aclose()


async def test_zu_kurzer_impuls_oeffnet_nicht(sim_modul):
    _, _, port = sim_modul
    treiber = WaveshareIo8("127.0.0.1", port=port)
    await treiber.open(1, 300)
    assert await treiber.is_locked(1) is True
    await treiber.aclose()


async def test_abbruch_schaltet_trotzdem_ab(sim_modul):
    """Wird die Anfrage mitten im Impuls abgebrochen, darf der Ausgang nicht an
    bleiben (Spule)."""
    _, modul, port = sim_modul
    treiber = WaveshareIo8("127.0.0.1", port=port)
    task = asyncio.create_task(treiber.open(5, 5000))
    await asyncio.sleep(0.3)
    assert modul.schloesser[4].ausgang is True
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.2)
    assert modul.schloesser[4].ausgang is False
    await treiber.aclose()


async def test_di_invertiert(sim_modul):
    _, _, port = sim_modul
    treiber = WaveshareIo8("127.0.0.1", port=port, di_invertiert=True)
    assert await treiber.is_locked(1) is False
    await treiber.aclose()


async def test_totes_modul_meldet_hardwarefehler(sim_modul):
    _, modul, port = sim_modul
    treiber = WaveshareIo8("127.0.0.1", port=port, timeout_s=0.3)
    assert await treiber.health() is True
    modul.online = False
    assert await treiber.health() is False
    with pytest.raises(HardwareFehler):
        await treiber.is_locked(1)
    await treiber.aclose()


async def test_ungueltiger_kanal(sim_modul):
    _, _, port = sim_modul
    treiber = WaveshareIo8("127.0.0.1", port=port)
    with pytest.raises(ValueError):
        await treiber.open(9, 1500)
    await treiber.aclose()
