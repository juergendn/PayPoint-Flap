"""Leser-Simulator: TCP-Server, der Kennungen wie der TWN4 zeilenweise ausgibt.

Der echte Treiber verbindet sich per pyserial `socket://hwsim:7000`.
"""

import asyncio
import logging

log = logging.getLogger("hwsim.leser")


class LeserSim:
    def __init__(self) -> None:
        self._clients: set[asyncio.StreamWriter] = set()

    @property
    def verbunden(self) -> int:
        return len(self._clients)

    async def _verbindung(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._clients.add(writer)
        log.info("Leser: Client verbunden")
        try:
            await reader.read()  # wartet bis der Client trennt
        finally:
            self._clients.discard(writer)
            writer.close()

    async def vorhalten(self, kennung: str) -> int:
        """Chip „vor den Leser halten“; liefert die Zahl der Empfänger."""
        zeile = f"{kennung.upper()}\r\n".encode("ascii")
        for writer in list(self._clients):
            try:
                writer.write(zeile)
                await writer.drain()
            except ConnectionError:
                self._clients.discard(writer)
        log.info("Leser: Chip %s an %d Client(s)", kennung, len(self._clients))
        return len(self._clients)

    async def starten(self, host: str = "0.0.0.0", port: int = 7000):
        return await asyncio.start_server(self._verbindung, host, port)
