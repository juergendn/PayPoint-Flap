"""Konfiguration aus Umgebungsvariablen (Präfix MVT_).

Hier steht nur, was vor dem DB-Zugriff bekannt sein muss oder je Gerät fest ist.
Fachliche Einstellungen (Impulsdauer, Fristen …) liegen in der Tabelle `einstellung`,
damit sie ohne neuen Container änderbar sind.
"""

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MVT_", env_file=".env")

    database_url: str = "postgresql+asyncpg://mvt:mvt@localhost:5432/mvt"
    automat_id: int = 1

    # Leser: "elatec_twn4" (seriell, auch socket://host:port für den Simulator)
    # oder "simulator" (rein im Prozess, für Tests).
    leser_treiber: str = "elatec_twn4"
    # Am MRX/MOROS.neo heißen die seriellen Ports /devices/<Slot>_serial<n>;
    # 1_serial1 ist die RS-485 des Grundgeräts.
    leser_url: str = "/devices/1_serial1"
    leser_baudrate: int = 9600

    # Nur für app.seed (Grundeinrichtung beim ersten Start): Adressen der IO-Module
    # in Reihenfolge #1,#2,… und ob Testmitarbeiter/-chips angelegt werden.
    # Standard = Automaten-LAN laut CLAUDE.md; die Entwicklung zeigt auf hwsim.
    seed_io: str = "192.168.10.11:502,192.168.10.12:502,192.168.10.13:502"
    seed_testdaten: bool = False

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def app_version() -> str:
    """Version aus pyproject.toml – liegt in der Entwicklung im Repo und im
    Container unter /opt/mvt/app neben dem Paket."""
    try:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        return tomllib.loads(pyproject.read_text())["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "?"
