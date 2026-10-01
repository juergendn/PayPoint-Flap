"""Schnittstelle für Schloss-Treiber (ein Objekt pro IO-Modul)."""

from typing import Protocol


class LockDriver(Protocol):
    async def open(self, kanal: int, dauer_ms: int) -> None:
        """Gibt einen Impuls auf den Kanal. Kehrt erst zurück, wenn der Ausgang
        wieder aus ist – der Ausgang darf nie dauerhaft an bleiben (Spule)."""
        ...

    async def is_locked(self, kanal: int) -> bool: ...

    async def health(self) -> bool: ...

    async def aclose(self) -> None:
        """Verbindung freigeben (beim Herunterfahren)."""
        ...
