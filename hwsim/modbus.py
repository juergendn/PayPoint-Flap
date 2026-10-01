"""Minimaler Modbus-TCP-Server im Stil des Waveshare IO 8CH.

Bewusst selbst geschrieben statt pymodbus-Server: Wir brauchen nur FC 1/2/5/15,
wollen das Verhalten (z. B. „Modul tot“) direkt steuern, und der pymodbus-
Datastore ist zum Wechsel auf v4 abgekündigt.

Coils 0–7 = Ausgänge, Discrete Inputs 0–7 = Schlossschalter (1 = verriegelt).
"""

import asyncio
import logging
import struct

from hwsim.anlage import Anlage, Modul

log = logging.getLogger("hwsim.modbus")

ILLEGAL_FUNCTION = 1
ILLEGAL_ADDRESS = 2
ILLEGAL_VALUE = 3


def _bits_packen(bits: list[bool]) -> bytes:
    daten = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            daten[i // 8] |= 1 << (i % 8)
    return bytes(daten)


class ModbusSimServer:
    def __init__(self, anlage: Anlage, modul: Modul) -> None:
        self.anlage = anlage
        self.modul = modul

    def verarbeiten(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        fehler = lambda code: bytes([fc | 0x80, code])  # noqa: E731
        schloesser = self.modul.schloesser
        n = len(schloesser)

        if fc in (1, 2):
            start, anzahl = struct.unpack(">HH", pdu[1:5])
            if anzahl < 1 or start + anzahl > n:
                return fehler(ILLEGAL_ADDRESS)
            werte = [
                s.ausgang if fc == 1 else s.verriegelt
                for s in schloesser[start : start + anzahl]
            ]
            daten = _bits_packen(werte)
            return bytes([fc, len(daten)]) + daten

        if fc == 5:
            adresse, wert = struct.unpack(">HH", pdu[1:5])
            if adresse >= n:
                return fehler(ILLEGAL_ADDRESS)
            if wert not in (0xFF00, 0x0000):
                return fehler(ILLEGAL_VALUE)
            self.anlage.setze_ausgang(self.modul, adresse, wert == 0xFF00)
            return pdu[:5]

        if fc == 15:
            start, anzahl, laenge = struct.unpack(">HHB", pdu[1:6])
            if anzahl < 1 or start + anzahl > n:
                return fehler(ILLEGAL_ADDRESS)
            daten = pdu[6 : 6 + laenge]
            for i in range(anzahl):
                an = bool(daten[i // 8] & (1 << (i % 8)))
                self.anlage.setze_ausgang(self.modul, start + i, an)
            return pdu[:5]

        return fehler(ILLEGAL_FUNCTION)

    async def _verbindung(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                kopf = await reader.readexactly(7)
                tid, _, laenge, unit = struct.unpack(">HHHB", kopf)
                pdu = await reader.readexactly(laenge - 1)
                if not self.modul.online:
                    # Totes Modul antwortet nicht – der Client läuft in den Timeout,
                    # genau wie bei gezogenem Kabel.
                    continue
                antwort = self.verarbeiten(pdu)
                writer.write(struct.pack(">HHHB", tid, 0, len(antwort) + 1, unit))
                writer.write(antwort)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def starten(self, host: str = "0.0.0.0", port: int | None = None):
        server = await asyncio.start_server(
            self._verbindung, host, port if port is not None else self.modul.port
        )
        log.info(
            "Modul %s lauscht auf %s", self.modul.name, server.sockets[0].getsockname()
        )
        return server
