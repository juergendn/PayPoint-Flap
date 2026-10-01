"""Schnittstelle für Leser-Treiber."""

from collections.abc import AsyncIterator
from typing import Protocol


class ReaderDriver(Protocol):
    def chips(self) -> AsyncIterator[str]:
        """Liefert jede gelesene Kennung als Hex-String (Großbuchstaben).
        Verbindungsabbrüche behandelt der Treiber selbst (Neuverbindung)."""
        ...

    async def health(self) -> bool: ...
