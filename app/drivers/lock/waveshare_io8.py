"""Waveshare Modbus POE ETH IO 8CH (Modbus TCP).

Kanal 1–8 → Coil 0–7 (Darlington-Ausgang) und Discrete Input 0–7.
Der Impuls wird hier per Software-Watchdog beendet (an → warten → aus). Die
eingebaute Impulsfunktion des Moduls (Flash-Befehl) nutzt eine nicht standardkonforme
FC05-Variante; ob wir sie zusätzlich als Absicherung setzen, klären wir am echten
Modul (Meilenstein 8).
"""

import asyncio
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from app.drivers.fehler import HardwareFehler

log = logging.getLogger(__name__)

KANAELE = 8
# Wie oft das Abschalten wiederholt wird, bevor wir aufgeben. Ein hängender
# Ausgang ist der gefährlichste Fehler (Spule überhitzt), daher großzügig.
ABSCHALT_VERSUCHE = 5


class WaveshareIo8:
    def __init__(
        self,
        adresse: str,
        port: int = 502,
        unit_id: int = 1,
        di_invertiert: bool = False,
        timeout_s: float = 1.0,
    ) -> None:
        self._name = f"{adresse}:{port}"
        self._unit_id = unit_id
        self._di_invertiert = di_invertiert
        self._client = AsyncModbusTcpClient(
            adresse,
            port=port,
            timeout=timeout_s,
            retries=1,
            reconnect_delay=1,
            reconnect_delay_max=10,
        )
        # Ein Modul, eine TCP-Verbindung: Anfragen strikt nacheinander, sonst
        # verheddern sich Antworten bei billigen Modulen.
        self._sperre = asyncio.Lock()

    async def _verbinden(self) -> None:
        if self._client.connected:
            return
        if not await self._client.connect():
            raise HardwareFehler(f"IO-Modul {self._name} nicht erreichbar")
        # Nach (Wieder-)Verbindung alle Ausgänge aus: falls die App mitten im
        # Impuls abgestürzt ist, darf kein Ausgang an bleiben.
        await self._client.write_coils(0, [False] * KANAELE, device_id=self._unit_id)
        log.info("IO-Modul %s verbunden, alle Ausgänge aus", self._name)

    async def _ausfuehren(self, aufruf):
        async with self._sperre:
            try:
                await self._verbinden()
                antwort = await aufruf()
            except (ModbusException, asyncio.TimeoutError, OSError) as e:
                self._client.close()
                raise HardwareFehler(f"IO-Modul {self._name}: {e}") from e
            if antwort.isError():
                raise HardwareFehler(f"IO-Modul {self._name}: {antwort}")
            return antwort

    def _pruefe_kanal(self, kanal: int) -> None:
        if not 1 <= kanal <= KANAELE:
            raise ValueError(f"Kanal {kanal} ungültig (1–{KANAELE})")

    async def _schalten(self, kanal: int, an: bool) -> None:
        await self._ausfuehren(
            lambda: self._client.write_coil(kanal - 1, an, device_id=self._unit_id)
        )

    async def _abschalten(self, kanal: int) -> None:
        for versuch in range(1, ABSCHALT_VERSUCHE + 1):
            try:
                await self._schalten(kanal, False)
                return
            except HardwareFehler:
                log.warning(
                    "Abschalten %s K%d fehlgeschlagen (Versuch %d)",
                    self._name,
                    kanal,
                    versuch,
                )
                await asyncio.sleep(0.2 * versuch)
        log.critical("Ausgang %s K%d evtl. noch AN!", self._name, kanal)
        raise HardwareFehler(
            f"Ausgang {self._name} K{kanal} ließ sich nicht abschalten"
        )

    async def open(self, kanal: int, dauer_ms: int) -> None:
        self._pruefe_kanal(kanal)
        await self._schalten(kanal, True)
        try:
            await asyncio.sleep(dauer_ms / 1000)
        finally:
            # shield: auch wenn die aufrufende Anfrage abgebrochen wird (Browser
            # zu), muss das Abschalten zu Ende laufen.
            await asyncio.shield(self._abschalten(kanal))

    async def is_locked(self, kanal: int) -> bool:
        self._pruefe_kanal(kanal)
        antwort = await self._ausfuehren(
            lambda: self._client.read_discrete_inputs(
                kanal - 1, count=1, device_id=self._unit_id
            )
        )
        return bool(antwort.bits[0]) != self._di_invertiert

    async def health(self) -> bool:
        try:
            await self._ausfuehren(
                lambda: self._client.read_coils(
                    0, count=KANAELE, device_id=self._unit_id
                )
            )
            return True
        except HardwareFehler:
            return False

    async def aclose(self) -> None:
        self._client.close()
