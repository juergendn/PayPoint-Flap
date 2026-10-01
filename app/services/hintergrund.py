"""Hintergrunddienste: Mailversand, Erinnerung, nächtliches Aufräumen.

Alle Aufgaben sind als einzelne Methoden aufrufbar (Tests); `starten()` lässt
sie in Schleifen laufen. Ein Fehler in einer Aufgabe beendet nie den Dienst.
"""

import asyncio
import logging
import smtplib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import einstellungen, mail
from app.core.protokoll import protokollieren
from app.db.models import Einstellung, Ereignis, Fach, Mail, Zuweisung
from app.web import ORTSZEIT, ortszeit

log = logging.getLogger(__name__)

MAIL_INTERVALL_S = 15
PRUEF_INTERVALL_S = 600
# Wartezeit nach dem n-ten Fehlversuch: 1, 2, 4 … höchstens 60 min.
MAX_WARTEN_MIN = 60
# ~2 Tage Wiederholung, dann aufgeben (status 'fehler', im Webinterface sichtbar).
MAX_VERSUCHE = 55
AUFRAEUMEN_STUNDE = 3  # Ortszeit
MAILS_BEHALTEN_TAGE = 30


def _jetzt() -> datetime:
    return datetime.now(UTC)


class Hintergrund:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._tasks: list[asyncio.Task] = []
        self._ohne_konfig_gemeldet = False

    def starten(self) -> None:
        self._tasks = [
            asyncio.create_task(
                self._schleife(self.mails_senden, MAIL_INTERVALL_S), name="mail"
            ),
            asyncio.create_task(
                self._schleife(self.pruefen, PRUEF_INTERVALL_S), name="pruefen"
            ),
        ]

    async def stoppen(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def _schleife(self, aufgabe, intervall_s: float) -> None:
        while True:
            try:
                await aufgabe()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Hintergrundaufgabe %s fehlgeschlagen", aufgabe.__name__)
            await asyncio.sleep(intervall_s)

    async def pruefen(self) -> None:
        await self.erinnern()
        await self.aufraeumen_wenn_faellig()

    # ---------- Mails ----------

    async def mails_senden(self) -> int:
        """Sendet fällige Mails; liefert die Zahl der gesendeten."""
        async with self._session_factory() as session:
            k = await mail.konfig(session)
            if k is None:
                if not self._ohne_konfig_gemeldet:
                    log.warning("SMTP nicht eingerichtet – Mails bleiben in der Queue")
                    self._ohne_konfig_gemeldet = True
                return 0
            self._ohne_konfig_gemeldet = False
            jetzt = _jetzt()
            faellig = list(
                await session.scalars(
                    select(Mail)
                    .where(
                        Mail.status == "offen",
                        (Mail.naechster_versuch.is_(None))
                        | (Mail.naechster_versuch <= jetzt),
                    )
                    .order_by(Mail.id)
                    .limit(20)
                )
            )
            gesendet = 0
            for m in faellig:
                try:
                    await mail.senden(k, m.empfaenger, m.betreff, m.text)
                except Exception as e:
                    m.versuche += 1
                    m.letzter_fehler = f"{type(e).__name__}: {e}"[:500]
                    if m.versuche >= MAX_VERSUCHE:
                        m.status = "fehler"
                        log.error("Mail %d aufgegeben: %s", m.id, m.letzter_fehler)
                    else:
                        warten = min(2 ** (m.versuche - 1), MAX_WARTEN_MIN)
                        m.naechster_versuch = _jetzt() + timedelta(minutes=warten)
                        log.warning(
                            "Mail %d: %s – neuer Versuch in %d min",
                            m.id,
                            m.letzter_fehler,
                            warten,
                        )
                    await session.commit()
                    # Kein Netz/Server: die übrigen Mails gar nicht erst probieren.
                    # (SMTPException erbt von OSError, ist aber ein Fehler dieser
                    # einen Mail, z. B. abgelehnter Empfänger.)
                    if isinstance(e, OSError) and not isinstance(
                        e, smtplib.SMTPException
                    ):
                        break
                    continue
                m.status = "gesendet"
                m.gesendet_am = _jetzt()
                m.letzter_fehler = None
                await session.commit()
                gesendet += 1
            return gesendet

    # ---------- Erinnerung ----------

    async def erinnern(self) -> int:
        """Eine Sammelmail an die Wäscheabteilung für Fächer, die länger als
        `erinnerung.tage` belegt sind. Jede Zuweisung wird nur einmal gemeldet."""
        async with self._session_factory() as session:
            empfaenger = await einstellungen.lesen(session, "mail.waesche")
            tage = await einstellungen.lesen_int(session, "erinnerung.tage", 5)
            grenze = _jetzt() - timedelta(days=tage)
            faellig = list(
                await session.scalars(
                    select(Zuweisung)
                    .join(Fach, Fach.id == Zuweisung.fach_id)
                    .where(
                        Fach.zustand == "belegt",
                        Zuweisung.abgeholt_am.is_(None),
                        Zuweisung.storniert.is_(False),
                        Zuweisung.erinnert_am.is_(None),
                        Zuweisung.befuellt_am < grenze,
                    )
                    .options(
                        selectinload(Zuweisung.fach),
                        selectinload(Zuweisung.mitarbeiter),
                    )
                    .order_by(Fach.nummer)
                )
            )
            if not faellig:
                return 0
            if not empfaenger:
                log.warning(
                    "%d Fächer überfällig, aber kein Empfänger Wäscheabteilung eingestellt",
                    len(faellig),
                )
                return 0
            zeilen = [
                f"  Fach {z.fach.nummer:>2}  {z.mitarbeiter.name} ({z.mitarbeiter.personalnummer})"
                f"  – befüllt am {ortszeit(z.befuellt_am)}"
                for z in faellig
            ]
            mail.einreihen(
                session,
                empfaenger,
                f"Klappenautomat: {len(faellig)} Fach/Fächer seit über {tage} Tagen nicht abgeholt",
                "Folgende Fächer wurden noch nicht abgeholt:\n\n"
                + "\n".join(zeilen)
                + "\n\nBitte die Mitarbeiter ansprechen oder die Zuweisung stornieren.",
            )
            jetzt = _jetzt()
            for z in faellig:
                z.erinnert_am = jetzt
                protokollieren(
                    session,
                    "erinnerung",
                    fach_id=z.fach_id,
                    mitarbeiter_id=z.mitarbeiter_id,
                )
            await session.commit()
            return len(faellig)

    # ---------- Aufräumen ----------

    async def aufraeumen_wenn_faellig(self) -> bool:
        """Einmal pro Nacht ab 03:00 Ortszeit. Der letzte Lauf steht in der DB,
        damit ein Neustart nicht zu doppelten oder ausgelassenen Läufen führt."""
        jetzt_lokal = datetime.now(ORTSZEIT)
        if jetzt_lokal.hour < AUFRAEUMEN_STUNDE:
            return False
        heute = jetzt_lokal.date().isoformat()
        async with self._session_factory() as session:
            if await einstellungen.lesen(session, "aufraeumen.letzter_lauf") == heute:
                return False
        await self.aufraeumen()
        async with self._session_factory() as session:
            eintrag = await session.get(Einstellung, "aufraeumen.letzter_lauf")
            if eintrag is None:
                session.add(
                    Einstellung(schluessel="aufraeumen.letzter_lauf", wert=heute)
                )
            else:
                eintrag.wert = heute
            await session.commit()
        return True

    async def aufraeumen(self) -> dict[str, int]:
        """Löscht Protokoll und abgeschlossene Zuweisungen älter als
        `protokoll.tage` (Datenschutz) sowie alte versendete Mails."""
        async with self._session_factory() as session:
            tage = await einstellungen.lesen_int(session, "protokoll.tage", 60)
            grenze = _jetzt() - timedelta(days=tage)
            ereignisse = (
                await session.execute(
                    delete(Ereignis).where(Ereignis.zeitpunkt < grenze)
                )
            ).rowcount
            zuweisungen = (
                await session.execute(
                    delete(Zuweisung).where(
                        ((Zuweisung.abgeholt_am < grenze))
                        | (
                            (Zuweisung.storniert.is_(True))
                            & (Zuweisung.befuellt_am < grenze)
                        )
                    )
                )
            ).rowcount
            mails = (
                await session.execute(
                    delete(Mail).where(
                        Mail.status.in_(("gesendet", "fehler")),
                        Mail.erstellt_am
                        < _jetzt() - timedelta(days=MAILS_BEHALTEN_TAGE),
                    )
                )
            ).rowcount
            ergebnis = {
                "ereignisse": ereignisse,
                "zuweisungen": zuweisungen,
                "mails": mails,
            }
            protokollieren(session, "aufraeumen", tage=tage, **ergebnis)
            await session.commit()
        log.info("Aufräumen: %s", ergebnis)
        return ergebnis
