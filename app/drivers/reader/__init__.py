"""Leser-Treiber: Auswahl über die Konfiguration (MVT_LESER_TREIBER)."""

from app.config import Settings
from app.drivers.reader.base import ReaderDriver
from app.drivers.reader.elatec_twn4 import ElatecTwn4Serial
from app.drivers.reader.simulator import SimulatorReader


def erzeuge(settings: Settings) -> ReaderDriver:
    if settings.leser_treiber == "elatec_twn4":
        return ElatecTwn4Serial(settings.leser_url, settings.leser_baudrate)
    if settings.leser_treiber == "simulator":
        return SimulatorReader()
    raise ValueError(f"Unbekannter Leser-Treiber '{settings.leser_treiber}'")
