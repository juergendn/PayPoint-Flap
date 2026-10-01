"""Modus bekleidung: Befüllen, Abholen, Stornieren, Anlernen, Sperren.

Alle zustandsändernden Abläufe laufen nacheinander (eine asyncio-Sperre pro
Automat): Chip-Scan, Webinterface und Türüberwachung können sonst dasselbe Fach
gleichzeitig anfassen. Ein Automat = ein Prozess, daher reicht die Sperre im
Speicher.

Jede Methode öffnet ihre eigene DB-Sitzung und committet selbst – die Aufrufer
(Leserdienst, Web, Überwachung) müssen nichts über Transaktionen wissen.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.faecher import Oeffnungsfehler, schloss_oeffnen
from app.core.mitarbeiter import kennung_normalisieren
from app.core.protokoll import protokollieren
from app.db.models import Benutzer, Chip, Fach, Mail, Mitarbeiter, Rolle, Zuweisung
from app.drivers.lock import SchlossRegistry

log = logging.getLogger(__name__)

ANLERNEN_DAUER_S = 60


class AblaufFehler(Exception):
    """Fachlich abgelehnter Vorgang; der Text ist für die Anzeige gedacht."""


@dataclass
class Anlernen:
    """Anlernmodus: der nächste unbekannte Chip wird erfasst."""

    bis: float = 0.0
    mitarbeiter_id: int | None = None
    benutzer_id: int | None = None

    @property
    def aktiv(self) -> bool:
        return time.monotonic() < self.bis

    @property
    def rest_s(self) -> int:
        return max(0, int(self.bis - time.monotonic()))


def _jetzt() -> datetime:
    return datetime.now(UTC)


def offene_zuweisung():
    return (Zuweisung.abgeholt_am.is_(None)) & (Zuweisung.storniert.is_(False))


class Bekleidung:
    def __init__(
        self,
        registry: SchlossRegistry,
        session_factory: Callable[[], AsyncSession],
    ) -> None:
        self.registry = registry
        self._session_factory = session_factory
        self._sperre = asyncio.Lock()
        self.anlernen = Anlernen()

    # ---------- Hilfen ----------

    async def _fach(self, session: AsyncSession, fach_id: int) -> Fach:
        fach = await session.get(
            Fach, fach_id, options=[selectinload(Fach.io_modul)], with_for_update=True
        )
        if fach is None or fach.automat_id != get_settings().automat_id:
            raise AblaufFehler("Fach unbekannt")
        return fach

    async def _oeffnen(
        self, session: AsyncSession, fach: Fach, benutzer_id: int | None
    ) -> None:
        """Öffnen; bei klemmendem Schloss Fach auf gestoert setzen."""
        # Vor dem Rollback merken – danach sind die ORM-Attribute verfallen.
        fach_id, nummer = fach.id, fach.nummer
        try:
            await schloss_oeffnen(session, self.registry, fach)
        except Oeffnungsfehler as e:
            await session.rollback()
            async with self._session_factory() as s:
                if e.grund == "mechanik":
                    f = await s.get(Fach, fach_id)
                    f.zustand = "gestoert"
                protokollieren(
                    s,
                    "stoerung",
                    fach_id=fach_id,
                    benutzer_id=benutzer_id,
                    grund=e.grund,
                    fehler=str(e),
                )
                await s.commit()
            log.error("%s", e)
            raise AblaufFehler(
                f"Fach {nummer} lässt sich nicht öffnen – Störung"
            ) from e

    # ---------- Befüllen ----------

    async def freies_fach(self, session: AsyncSession) -> Fach | None:
        return await session.scalar(
            select(Fach)
            .where(
                Fach.automat_id == get_settings().automat_id,
                Fach.zustand == "frei",
                Fach.gesperrt.is_(False),
                Fach.io_modul_id.is_not(None),
            )
            .order_by(Fach.nummer)
            .limit(1)
        )

    async def befuellen(
        self, mitarbeiter_id: int, benutzer_id: int | None, fach_id: int | None = None
    ) -> int:
        """Fach öffnen und dem Mitarbeiter zuweisen. Liefert die Fachnummer.

        Ohne fach_id nimmt der Automat das niedrigste freie Fach.
        """
        async with self._sperre, self._session_factory() as session:
            ma = await session.get(Mitarbeiter, mitarbeiter_id)
            if ma is None or not ma.aktiv:
                raise AblaufFehler("Mitarbeiter unbekannt oder inaktiv")
            vorhanden = await session.scalar(
                select(Fach.nummer)
                .join(Zuweisung, Zuweisung.fach_id == Fach.id)
                .where(Zuweisung.mitarbeiter_id == ma.id, offene_zuweisung())
            )
            if vorhanden is not None:
                raise AblaufFehler(f"{ma.name} hat schon Fach {vorhanden}")

            if fach_id is None:
                fach = await self.freies_fach(session)
                if fach is None:
                    raise AblaufFehler("Kein freies Fach")
                fach = await self._fach(session, fach.id)
            else:
                fach = await self._fach(session, fach_id)
            if fach.gesperrt:
                raise AblaufFehler(f"Fach {fach.nummer} ist gesperrt")
            if fach.zustand != "frei":
                raise AblaufFehler(f"Fach {fach.nummer} ist nicht frei")

            await self._oeffnen(session, fach, benutzer_id)
            fach.zustand = "befuellung"
            session.add(
                Zuweisung(
                    fach_id=fach.id,
                    mitarbeiter_id=ma.id,
                    befuellt_von=benutzer_id,
                    storniert=False,
                )
            )
            protokollieren(
                session,
                "befuellung_begonnen",
                fach_id=fach.id,
                mitarbeiter_id=ma.id,
                benutzer_id=benutzer_id,
            )
            await session.commit()
            return fach.nummer

    # ---------- Stornieren ----------

    async def stornieren(self, fach_id: int, benutzer_id: int | None) -> int:
        """Zuweisung aufheben und Fach zum Ausräumen öffnen."""
        async with self._sperre, self._session_factory() as session:
            fach = await self._fach(session, fach_id)
            zuweisung = await session.scalar(
                select(Zuweisung).where(
                    Zuweisung.fach_id == fach.id, offene_zuweisung()
                )
            )
            if zuweisung is None:
                raise AblaufFehler(f"Fach {fach.nummer} hat keine Zuweisung")
            # Steht die Tür noch offen (Befüllung läuft), muss nichts geöffnet werden.
            if fach.zustand != "befuellung":
                await self._oeffnen(session, fach, benutzer_id)
            zuweisung.storniert = True
            fach.zustand = "entnahme"
            protokollieren(
                session,
                "zuweisung_storniert",
                fach_id=fach.id,
                mitarbeiter_id=zuweisung.mitarbeiter_id,
                benutzer_id=benutzer_id,
            )
            await session.commit()
            return fach.nummer

    # ---------- Manuell: öffnen, sperren, Störung ----------

    async def oeffnen_manuell(self, fach_id: int, benutzer_id: int | None) -> int:
        """Öffnen ohne Zustandswechsel (Kontrolle, Reinigung)."""
        async with self._sperre, self._session_factory() as session:
            fach = await self._fach(session, fach_id)
            await self._oeffnen(session, fach, benutzer_id)
            protokollieren(
                session,
                "fach_geoeffnet",
                fach_id=fach.id,
                benutzer_id=benutzer_id,
                quelle="manuell",
            )
            await session.commit()
            return fach.nummer

    async def sperren(
        self, fach_id: int, gesperrt: bool, benutzer_id: int | None
    ) -> None:
        async with self._sperre, self._session_factory() as session:
            fach = await self._fach(session, fach_id)
            fach.gesperrt = gesperrt
            protokollieren(
                session,
                "fach_gesperrt" if gesperrt else "fach_entsperrt",
                fach_id=fach.id,
                benutzer_id=benutzer_id,
            )
            await session.commit()

    async def stoerung_quittieren(self, fach_id: int, benutzer_id: int | None) -> str:
        """Nach Behebung: Zustand aus der offenen Zuweisung ableiten."""
        async with self._sperre, self._session_factory() as session:
            fach = await self._fach(session, fach_id)
            if fach.zustand != "gestoert":
                raise AblaufFehler(f"Fach {fach.nummer} ist nicht gestört")
            offen = await session.scalar(
                select(Zuweisung.id).where(
                    Zuweisung.fach_id == fach.id, offene_zuweisung()
                )
            )
            fach.zustand = "belegt" if offen else "frei"
            protokollieren(
                session,
                "stoerung_quittiert",
                fach_id=fach.id,
                benutzer_id=benutzer_id,
                neuer_zustand=fach.zustand,
            )
            await session.commit()
            return fach.zustand

    # ---------- Türkontakt ----------

    async def tuer_geschlossen(self, fach_id: int) -> None:
        """Von der Türüberwachung: Tür eines offenen Vorgangs ist zu."""
        async with self._sperre, self._session_factory() as session:
            fach = await self._fach(session, fach_id)
            if fach.zustand == "befuellung":
                zuweisung = await session.scalar(
                    select(Zuweisung)
                    .where(Zuweisung.fach_id == fach.id, offene_zuweisung())
                    .options(selectinload(Zuweisung.mitarbeiter))
                )
                if zuweisung is None:  # zwischenzeitlich storniert
                    fach.zustand = "frei"
                else:
                    fach.zustand = "belegt"
                    zuweisung.befuellt_am = _jetzt()
                    self._mail_befuellt(session, fach, zuweisung.mitarbeiter)
                protokollieren(
                    session,
                    "fach_befuellt" if zuweisung else "fach_frei",
                    fach_id=fach.id,
                    mitarbeiter_id=zuweisung.mitarbeiter_id if zuweisung else None,
                )
            elif fach.zustand == "entnahme":
                fach.zustand = "frei"
                protokollieren(session, "fach_frei", fach_id=fach.id)
            else:
                return
            await session.commit()
            log.info("Fach %d: Tür zu → %s", fach.nummer, fach.zustand)

    def _mail_befuellt(
        self, session: AsyncSession, fach: Fach, ma: Mitarbeiter
    ) -> None:
        # Nur in die Queue – versendet wird vom Maildienst (auch ohne 4G kein Fehler).
        if not ma.email:
            return
        session.add(
            Mail(
                empfaenger=ma.email,
                betreff=f"Deine Kleidung liegt in Fach {fach.nummer}",
                text=(
                    f"Hallo {ma.name},\n\n"
                    f"deine Kleidung liegt im Klappenautomaten in Fach {fach.nummer} "
                    "für dich bereit. Halte deinen Chip an den Leser, das Fach "
                    "öffnet sich dann.\n\nDeine Wäscheabteilung"
                ),
                status="offen",
                versuche=0,
            )
        )

    # ---------- Chip am Leser ----------

    async def chip(self, kennung: str) -> dict[str, Any]:
        """Reaktion auf einen gelesenen Chip. Liefert eine Meldung fürs Display:
        {"art": abholung|angelernt|menue|kein_fach|unbekannt|gesperrt|fehler, …}"""
        async with self._sperre:
            async with self._session_factory() as session:
                chip = await session.scalar(
                    select(Chip)
                    .where(Chip.kennung == kennung)
                    .options(selectinload(Chip.mitarbeiter))
                )
                ma = chip.mitarbeiter if chip and chip.aktiv else None
                if ma is not None and not ma.aktiv:
                    ma = None
                protokollieren(
                    session,
                    "chip_gelesen",
                    chip_id=chip.id if chip else None,
                    mitarbeiter_id=ma.id if ma else None,
                    kennung=kennung,
                    bekannt=chip is not None,
                )
                await session.commit()

                if chip is None:
                    if self.anlernen.aktiv:
                        return await self._anlernen(session, kennung)
                    return {"art": "unbekannt", "kennung": kennung}
                if not chip.aktiv:
                    return {"art": "gesperrt", "kennung": kennung}
                if ma is None:
                    return {"art": "nicht_zugeordnet", "kennung": kennung}

                benutzer = await session.scalar(
                    select(Benutzer)
                    .where(Benutzer.mitarbeiter_id == ma.id, Benutzer.aktiv)
                    .options(selectinload(Benutzer.rolle).selectinload(Rolle.rechte))
                )
                fach = await session.scalar(
                    select(Fach)
                    .join(Zuweisung, Zuweisung.fach_id == Fach.id)
                    .where(Zuweisung.mitarbeiter_id == ma.id, offene_zuweisung())
                )

            basis = {"name": ma.name, "mitarbeiter_id": ma.id}
            # Wäsche/Admin bekommen am Display ihr Menü (Meilenstein 5) – mit dem
            # eigenen Fach als Option, statt es ungefragt zu öffnen.
            if benutzer and "fach_befuellen" in benutzer.rechte:
                return {
                    "art": "menue",
                    "benutzer_id": benutzer.id,
                    "eigenes_fach": fach.nummer if fach else None,
                    **basis,
                }
            if fach is None:
                return {"art": "kein_fach", **basis}
            return await self._abholen(fach.id, **basis)

    async def abholen(self, mitarbeiter_id: int) -> dict[str, Any]:
        """Abholung ohne Chip-Kontext (z. B. Menü am Display)."""
        async with self._sperre:
            async with self._session_factory() as session:
                ma = await session.get(Mitarbeiter, mitarbeiter_id)
                fach_id = await session.scalar(
                    select(Fach.id)
                    .join(Zuweisung, Zuweisung.fach_id == Fach.id)
                    .where(
                        Zuweisung.mitarbeiter_id == mitarbeiter_id, offene_zuweisung()
                    )
                )
                if ma is None or fach_id is None:
                    return {"art": "kein_fach"}
                name = ma.name
            return await self._abholen(
                fach_id, mitarbeiter_id=mitarbeiter_id, name=name
            )

    async def _abholen(self, fach_id: int, *, mitarbeiter_id: int, name: str) -> dict:
        basis = {"name": name, "mitarbeiter_id": mitarbeiter_id}
        async with self._session_factory() as session:
            fach = await self._fach(session, fach_id)
            nummer = fach.nummer
            if fach.gesperrt:
                return {"art": "fach_gesperrt", "fach": nummer, **basis}
            if fach.zustand == "befuellung":
                return {"art": "noch_nicht_bereit", "fach": fach.nummer, **basis}
            if fach.zustand != "belegt":
                return {
                    "art": "fehler",
                    "fach": fach.nummer,
                    **basis,
                    "text": "Fach nicht abholbereit",
                }
            try:
                await self._oeffnen(session, fach, None)
            except AblaufFehler as e:
                return {"art": "fehler", "fach": nummer, "text": str(e), **basis}
            zuweisung = await session.scalar(
                select(Zuweisung).where(
                    Zuweisung.fach_id == fach.id, offene_zuweisung()
                )
            )
            zuweisung.abgeholt_am = _jetzt()
            fach.zustand = "entnahme"
            protokollieren(
                session, "abholung", fach_id=fach.id, mitarbeiter_id=mitarbeiter_id
            )
            await session.commit()
            return {"art": "abholung", "fach": fach.nummer, **basis}

    # ---------- Anlernen ----------

    def anlernen_starten(
        self, benutzer_id: int | None, mitarbeiter_id: int | None = None
    ) -> None:
        self.anlernen = Anlernen(
            bis=time.monotonic() + ANLERNEN_DAUER_S,
            mitarbeiter_id=mitarbeiter_id,
            benutzer_id=benutzer_id,
        )

    def anlernen_beenden(self) -> None:
        self.anlernen = Anlernen()

    async def _anlernen(self, session: AsyncSession, kennung: str) -> dict:
        anlernen = self.anlernen
        self.anlernen = Anlernen()  # genau ein Chip pro Anlernvorgang
        normal = kennung_normalisieren(kennung)
        if normal is None:
            return {"art": "fehler", "text": f"Kennung {kennung} ungültig"}
        chip = Chip(kennung=normal, mitarbeiter_id=anlernen.mitarbeiter_id, aktiv=True)
        session.add(chip)
        await session.flush()
        protokollieren(
            session,
            "chip_angelernt",
            chip_id=chip.id,
            mitarbeiter_id=anlernen.mitarbeiter_id,
            benutzer_id=anlernen.benutzer_id,
        )
        await session.commit()
        name = None
        if anlernen.mitarbeiter_id:
            ma = await session.get(Mitarbeiter, anlernen.mitarbeiter_id)
            name = ma.name if ma else None
        return {"art": "angelernt", "kennung": normal, "name": name}
