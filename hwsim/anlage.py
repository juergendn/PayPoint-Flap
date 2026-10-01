"""Physik der Schlösser KR-S70N und Türen, unabhängig vom Protokoll."""

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("hwsim")


@dataclass
class Schloss:
    ausgang: bool = False
    ausgang_seit: float | None = None
    ausgeloest: bool = False  # in diesem Impuls schon entriegelt?
    ueberhitzt_gemeldet: bool = False
    verriegelt: bool = True
    tuer_offen_seit: float | None = None


@dataclass
class Modul:
    name: str
    port: int
    schloesser: list[Schloss] = field(
        default_factory=lambda: [Schloss() for _ in range(8)]
    )
    online: bool = True


class Anlage:
    def __init__(
        self,
        ports: list[int],
        min_impuls_ms: int = 1000,
        tuer_zu_nach_s: float = 8.0,
        max_ausgang_s: float = 5.0,
    ) -> None:
        self.module = [Modul(f"#{i + 1}", p) for i, p in enumerate(ports)]
        self.min_impuls_s = min_impuls_ms / 1000
        self.tuer_zu_nach_s = tuer_zu_nach_s
        self.max_ausgang_s = max_ausgang_s

    def setze_ausgang(self, modul: Modul, index: int, an: bool) -> None:
        schloss = modul.schloesser[index]
        if an and not schloss.ausgang:
            schloss.ausgang_seit = time.monotonic()
            schloss.ausgeloest = False
            schloss.ueberhitzt_gemeldet = False
        elif not an and schloss.ausgang:
            dauer = time.monotonic() - (schloss.ausgang_seit or 0)
            if not schloss.ausgeloest:
                log.warning(
                    "Modul %s K%d: Impuls %.0f ms zu kurz – Schloss bleibt zu",
                    modul.name,
                    index + 1,
                    dauer * 1000,
                )
            schloss.ausgang_seit = None
        schloss.ausgang = an

    def tick(self) -> None:
        jetzt = time.monotonic()
        for modul in self.module:
            for i, s in enumerate(modul.schloesser):
                if s.ausgang and s.ausgang_seit is not None:
                    dauer = jetzt - s.ausgang_seit
                    # Kerong: entriegelt einmal pro Impuls, wenn er lang genug ist.
                    if not s.ausgeloest and dauer >= self.min_impuls_s:
                        s.ausgeloest = True
                        self.oeffnen(modul, i)
                    if dauer > self.max_ausgang_s and not s.ueberhitzt_gemeldet:
                        s.ueberhitzt_gemeldet = True
                        log.error(
                            "Modul %s K%d: Ausgang seit %.1f s an – Spule überhitzt!",
                            modul.name,
                            i + 1,
                            dauer,
                        )
                if (
                    not s.verriegelt
                    and self.tuer_zu_nach_s > 0
                    and s.tuer_offen_seit is not None
                    and jetzt - s.tuer_offen_seit >= self.tuer_zu_nach_s
                ):
                    self.schliessen(modul, i)

    def oeffnen(self, modul: Modul, index: int) -> None:
        """Entriegeln (Impuls oder Nothebel): Feder drückt die Tür auf."""
        s = modul.schloesser[index]
        if s.verriegelt:
            log.info("Modul %s K%d: Tür auf", modul.name, index + 1)
        s.verriegelt = False
        s.tuer_offen_seit = time.monotonic()

    def schliessen(self, modul: Modul, index: int) -> None:
        """Tür zudrücken: Haken rastet ein, Schalter meldet verriegelt."""
        s = modul.schloesser[index]
        if not s.verriegelt:
            log.info("Modul %s K%d: Tür zu", modul.name, index + 1)
        s.verriegelt = True
        s.tuer_offen_seit = None

    def status(self) -> list[dict]:
        return [
            {
                "name": m.name,
                "port": m.port,
                "online": m.online,
                "kanaele": [
                    {"ausgang": s.ausgang, "verriegelt": s.verriegelt}
                    for s in m.schloesser
                ],
            }
            for m in self.module
        ]
