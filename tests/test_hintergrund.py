"""Hintergrunddienste: Mail-Queue mit Wiederholung, Erinnerung, Aufräumen,
Meldung „Tür zu lange offen“."""

import smtplib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core import mail
from app.db.models import (
    Einstellung,
    Ereignis,
    Fach,
    IoModul,
    Mail,
    Mitarbeiter,
    Zuweisung,
)
from app.db.session import SessionFactory
from app.services.hintergrund import Hintergrund

ALT = datetime.now(UTC) - timedelta(days=100)


@pytest.fixture
def gesendet(monkeypatch):
    """Ersetzt den SMTP-Versand; die Liste sammelt (an, betreff)."""
    liste: list[tuple[str, str]] = []

    async def senden(k, empfaenger, betreff, text):
        liste.append((empfaenger, betreff))

    monkeypatch.setattr(mail, "senden", senden)
    return liste


async def _smtp(db):
    for k, v in {
        "smtp.host": "mail.test",
        "smtp.absender": "a@test",
        "mail.waesche": "w@test",
    }.items():
        db.add(Einstellung(schluessel=k, wert=v))
    await db.commit()


async def test_ohne_smtp_bleibt_mail_liegen(db, gesendet):
    mail.einreihen(db, "x@test", "Betreff", "Text")
    await db.commit()
    assert await Hintergrund(SessionFactory).mails_senden() == 0
    m = await db.scalar(select(Mail))
    assert m.status == "offen" and m.versuche == 0  # kein Versuch gezählt


async def test_versand(db, gesendet):
    await _smtp(db)
    mail.einreihen(db, "x@test", "Hallo", "Text")
    await db.commit()
    assert await Hintergrund(SessionFactory).mails_senden() == 1
    assert gesendet == [("x@test", "Hallo")]
    db.expire_all()
    assert (await db.scalar(select(Mail))).status == "gesendet"


async def test_kein_netz_wiederholung_mit_abstand(db, monkeypatch):
    await _smtp(db)
    mail.einreihen(db, "a@test", "1", "")
    mail.einreihen(db, "b@test", "2", "")
    await db.commit()
    versuche = []

    async def kein_netz(k, *a):
        versuche.append(a[0])
        raise ConnectionRefusedError("kein Netz")

    monkeypatch.setattr(mail, "senden", kein_netz)
    dienst = Hintergrund(SessionFactory)
    await dienst.mails_senden()
    assert versuche == ["a@test"]  # nach Netzfehler nicht weiterprobieren
    db.expire_all()
    erste = await db.scalar(select(Mail).order_by(Mail.id))
    assert erste.versuche == 1 and erste.naechster_versuch > datetime.now(UTC)
    # Noch nicht fällig → kein neuer Versuch
    await dienst.mails_senden()
    assert versuche == ["a@test", "b@test"]


async def test_abgelehnter_empfaenger_blockiert_nicht(db, monkeypatch):
    await _smtp(db)
    mail.einreihen(db, "falsch@test", "1", "")
    mail.einreihen(db, "gut@test", "2", "")
    await db.commit()
    ok = []

    async def senden(k, empfaenger, *a):
        if empfaenger.startswith("falsch"):
            raise smtplib.SMTPRecipientsRefused({empfaenger: (550, b"unbekannt")})
        ok.append(empfaenger)

    monkeypatch.setattr(mail, "senden", senden)
    await Hintergrund(SessionFactory).mails_senden()
    assert ok == ["gut@test"]


async def _belegt(db, befuellt_am, abgeholt_am=None):
    db.add(Mitarbeiter(id=70, personalnummer="70", name="Otto Offen", aktiv=True))
    db.add(
        Fach(
            id=80,
            automat_id=1,
            nummer=9,
            zustand="belegt" if not abgeholt_am else "frei",
            gesperrt=False,
        )
    )
    await db.flush()
    db.add(
        Zuweisung(
            fach_id=80,
            mitarbeiter_id=70,
            befuellt_am=befuellt_am,
            abgeholt_am=abgeholt_am,
            storniert=False,
        )
    )
    await db.commit()


async def test_erinnerung_einmal(db):
    await _smtp(db)
    await _belegt(db, datetime.now(UTC) - timedelta(days=6))
    dienst = Hintergrund(SessionFactory)
    assert await dienst.erinnern() == 1
    assert await dienst.erinnern() == 0  # nicht doppelt
    m = await db.scalar(select(Mail))
    assert m.empfaenger == "w@test" and "Fach  9" in m.text and "Otto Offen" in m.text


async def test_erinnerung_noch_nicht_faellig(db):
    await _smtp(db)
    await _belegt(db, datetime.now(UTC) - timedelta(days=2))
    assert await Hintergrund(SessionFactory).erinnern() == 0


async def test_aufraeumen(db):
    await _belegt(db, ALT, abgeholt_am=ALT)
    db.add(Ereignis(automat_id=1, art="abholung", zeitpunkt=ALT))
    db.add(Ereignis(automat_id=1, art="abholung"))
    await db.commit()
    ergebnis = await Hintergrund(SessionFactory).aufraeumen()
    assert ergebnis["ereignisse"] == 1 and ergebnis["zuweisungen"] == 1
    db.expire_all()
    assert await db.scalar(select(func.count(Zuweisung.id))) == 0
    # übrig: das frische Ereignis + der Aufräum-Eintrag
    assert await db.scalar(select(func.count(Ereignis.id))) == 2


async def test_aufraeumen_offene_zuweisung_bleibt(db):
    await _belegt(db, ALT)
    await Hintergrund(SessionFactory).aufraeumen()
    assert await db.scalar(select(func.count(Zuweisung.id))) == 1


async def test_tuer_zu_lange_offen(db, monkeypatch):
    from app.drivers.lock import SchlossRegistry
    from app.modes.bekleidung.ablauf import Bekleidung
    from app.services import tuerkontakte
    from app.services.tuerkontakte import Tuerueberwachung

    await _smtp(db)
    modul = IoModul(
        automat_id=1,
        name="#1",
        treiber="simulator",
        adresse="s",
        port=0,
        unit_id=1,
        di_invertiert=False,
    )
    db.add(modul)
    await db.flush()
    db.add(
        Fach(
            automat_id=1,
            nummer=2,
            io_modul_id=modul.id,
            kanal=1,
            zustand="frei",
            gesperrt=False,
        )
    )
    await db.commit()
    registry = SchlossRegistry()
    registry.laden([modul])
    registry.fuer_modul(modul.id).verriegelt[1] = False  # Nothebel gezogen
    ueberwachung = Tuerueberwachung(
        registry, SessionFactory, Bekleidung(registry, SessionFactory)
    )

    uhr = [1000.0]
    monkeypatch.setattr(tuerkontakte.time, "monotonic", lambda: uhr[0])
    await ueberwachung.pruefen()
    uhr[0] += 11 * 60
    await ueberwachung.pruefen()
    await ueberwachung.pruefen()  # nur einmal melden
    arten = list(
        await db.scalars(select(Ereignis.art).where(Ereignis.art == "tuer_offen_lange"))
    )
    assert len(arten) == 1
    assert "Fach 2 steht offen" in (await db.scalar(select(Mail))).betreff
