"""ELATEC TWN4 Palon Compact Panel an RS-485 (MRX/MOROS.neo `/devices/1_serial1`).

Der TWN4 sendet nur, wir hören nur zu – deshalb gibt es auf dem halbduplexen
RS-485 keine Richtungsumschaltung zu beachten.

Erwartet pro Chip eine Textzeile mit der Kennung in Hex (TWN4-Standard-App,
Abschluss CR oder CR/LF). Das genaue Ausgabeformat ist noch offen und wird am
echten Leser festgelegt.

`url` wird an pyserial.serial_for_url übergeben: am Gerät z. B. `/dev/ttyS0`,
in der Entwicklung `socket://hwsim:7000` – so läuft derselbe Code gegen den
Simulator wie gegen die Hardware.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator

import serial

log = logging.getLogger(__name__)

HEX = re.compile(r"^[0-9A-F]+$")


class ElatecTwn4Serial:
    def __init__(self, url: str, baudrate: int = 9600, neuversuch_s: float = 3.0):
        self._url = url
        self._baudrate = baudrate
        self._neuversuch_s = neuversuch_s
        self._verbunden = False

    def _oeffnen(self) -> serial.SerialBase:
        # timeout: readline kehrt regelmäßig zurück, damit Abbruch möglich bleibt.
        return serial.serial_for_url(self._url, baudrate=self._baudrate, timeout=1)

    async def chips(self) -> AsyncIterator[str]:
        while True:
            try:
                port = await asyncio.to_thread(self._oeffnen)
            except (serial.SerialException, OSError) as e:
                self._verbunden = False
                log.warning("Leser %s nicht erreichbar: %s", self._url, e)
                await asyncio.sleep(self._neuversuch_s)
                continue

            self._verbunden = True
            log.info("Leser %s verbunden", self._url)
            puffer = b""
            try:
                while True:
                    daten = await asyncio.to_thread(port.read_until, b"\r", 64)
                    puffer += daten
                    # Zeile erst auswerten, wenn sie abgeschlossen ist – read_until
                    # liefert bei Timeout auch Bruchstücke.
                    while b"\r" in puffer or b"\n" in puffer:
                        zeile, puffer = re.split(rb"[\r\n]", puffer, maxsplit=1)
                        kennung = zeile.decode("ascii", "ignore").strip().upper()
                        if HEX.match(kennung):
                            yield kennung
                        elif kennung:
                            log.warning("Leser: unerwartete Zeile %r", kennung)
            except (serial.SerialException, OSError) as e:
                log.warning("Leser %s getrennt: %s", self._url, e)
            finally:
                self._verbunden = False
                await asyncio.to_thread(port.close)
            await asyncio.sleep(self._neuversuch_s)

    async def health(self) -> bool:
        return self._verbunden
