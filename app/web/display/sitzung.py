"""Display-Sitzung: Wäsche/Admin melden sich am Panel per Chip an.

Es gibt genau ein Display und einen Leser, daher höchstens eine Sitzung. Das
Token geht per SSE ans Display und muss jede Aktion begleiten (Kopf
`X-Display-Token`). Ablauf nach `display.timeout_s` ohne Bedienung – ein
vergessenes Menü soll niemandem Rechte überlassen.
"""

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from app.core import einstellungen
from app.db.session import SessionFactory


@dataclass
class DisplaySitzung:
    token: str
    benutzer_id: int
    mitarbeiter_id: int
    name: str
    rechte: set[str] = field(default_factory=set)
    timeout_s: int = 60
    bis: float = 0.0

    def verlaengern(self) -> None:
        self.bis = time.monotonic() + self.timeout_s

    @property
    def gueltig(self) -> bool:
        return time.monotonic() < self.bis


class DisplaySitzungen:
    def __init__(self) -> None:
        self.aktuell: DisplaySitzung | None = None

    async def anmelden(self, meldung: dict[str, Any]) -> str:
        async with SessionFactory() as session:
            timeout_s = await einstellungen.lesen_int(session, "display.timeout_s", 60)
        sitzung = DisplaySitzung(
            token=secrets.token_urlsafe(24),
            benutzer_id=meldung["benutzer_id"],
            mitarbeiter_id=meldung["mitarbeiter_id"],
            name=meldung["name"],
            rechte=set(meldung.get("rechte", [])),
            timeout_s=timeout_s,
        )
        sitzung.verlaengern()
        self.aktuell = sitzung
        return sitzung.token

    def pruefen(self, token: str | None) -> DisplaySitzung | None:
        s = self.aktuell
        if s is None or not token or not secrets.compare_digest(s.token, token):
            return None
        if not s.gueltig:
            self.aktuell = None
            return None
        s.verlaengern()
        return s

    def beenden(self) -> None:
        self.aktuell = None

    async def chip_meldung(self, meldung: dict[str, Any]) -> dict[str, Any]:
        """Hängt sich zwischen Modus und Display: Menü-Chip → Sitzung öffnen.
        Ein anderer Chip beendet eine offene Sitzung (wer jetzt vor dem Panel
        steht, ist nicht mehr die Wäscheabteilung) – außer beim Anlernen, das
        ja gerade aus der Sitzung heraus läuft."""
        if meldung.get("art") == "menue":
            meldung = {**meldung, "token": await self.anmelden(meldung)}
        elif meldung.get("art") != "angelernt":
            self.beenden()
        return meldung
