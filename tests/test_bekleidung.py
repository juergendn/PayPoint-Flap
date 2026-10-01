"""Modus bekleidung: Zustandsmaschine mit simuliertem Schloss und Türüberwachung."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models import (
    Benutzer,
    Chip,
    Ereignis,
    Fach,
    IoModul,
    Mail,
    Mitarbeiter,
    Rolle,
    Zuweisung,
)
from app.db.session import SessionFactory
from app.drivers.lock import SchlossRegistry
from app.modes.bekleidung.ablauf import AblaufFehler, Bekleidung
from app.services.tuerkontakte import Tuerueberwachung


@pytest.fixture
async def anlage(db):
    """3 Fächer an einem simulierten Modul, zwei Mitarbeiter mit Chip."""
    modul = IoModul(
        automat_id=1,
        name="#1",
        treiber="simulator",
        adresse="sim",
        port=0,
        unit_id=1,
        di_invertiert=False,
    )
    db.add(modul)
    await db.flush()
    for nr in (2, 3, 4):
        db.add(
            Fach(
                automat_id=1,
                nummer=nr,
                io_modul_id=modul.id,
                kanal=nr - 1,
                zustand="frei",
                gesperrt=False,
            )
        )
    anna = Mitarbeiter(
        personalnummer="1", name="Anna", email="anna@example.org", aktiv=True
    )
    bernd = Mitarbeiter(personalnummer="2", name="Bernd", aktiv=True)
    db.add_all([anna, bernd])
    await db.flush()
    db.add_all(
        [
            Chip(kennung="AA01", mitarbeiter_id=anna.id, aktiv=True),
            Chip(kennung="BB02", mitarbeiter_id=bernd.id, aktiv=True),
        ]
    )
    await db.commit()

    # Als einfache Werte: die Tests rufen db.expire_all() auf, danach wären
    # ORM-Objekte verfallen und ein Attributzugriff bräuchte DB-IO.
    anna = SimpleNamespace(id=anna.id, name=anna.name)
    bernd = SimpleNamespace(id=bernd.id, name=bernd.name)
    registry = SchlossRegistry()
    registry.laden([modul])
    modus = Bekleidung(registry, SessionFactory)
    ueberwachung = Tuerueberwachung(registry, SessionFactory, modus)
    schloss = registry.fuer_modul(modul.id)
    return modus, ueberwachung, schloss, anna, bernd


async def _fach(db, nummer):
    db.expire_all()
    return await db.scalar(select(Fach).where(Fach.nummer == nummer))


async def test_befuellen_und_abholen(anlage, db):
    modus, ueberwachung, schloss, anna, _ = anlage

    assert await modus.befuellen(anna.id, None) == 2  # niedrigstes freies Fach
    assert (await _fach(db, 2)).zustand == "befuellung"
    assert schloss.verriegelt[1] is False

    await ueberwachung.pruefen()  # Tür noch offen → bleibt
    assert (await _fach(db, 2)).zustand == "befuellung"

    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    assert (await _fach(db, 2)).zustand == "belegt"
    mail = await db.scalar(select(Mail))
    assert mail.empfaenger == "anna@example.org" and "Fach 2" in mail.betreff

    meldung = await modus.chip("AA01")
    assert meldung == {
        "art": "abholung",
        "fach": 2,
        "name": "Anna",
        "mitarbeiter_id": anna.id,
    }
    assert (await _fach(db, 2)).zustand == "entnahme"
    zuweisung = await db.scalar(select(Zuweisung))
    assert zuweisung.abgeholt_am is not None

    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    assert (await _fach(db, 2)).zustand == "frei"


async def test_fach_erst_frei_wenn_tuer_zu(anlage, db):
    modus, ueberwachung, schloss, anna, _ = anlage
    await modus.befuellen(anna.id, None)
    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    await modus.chip("AA01")
    for _ in range(3):  # Tür bleibt offen stehen
        await ueberwachung.pruefen()
    assert (await _fach(db, 2)).zustand == "entnahme"


async def test_nur_eine_zuweisung_pro_mitarbeiter(anlage):
    modus, _, _, anna, _ = anlage
    await modus.befuellen(anna.id, None)
    with pytest.raises(AblaufFehler, match="hat schon Fach 2"):
        await modus.befuellen(anna.id, None)


async def test_belegtes_fach_nicht_doppelt(anlage):
    modus, _, _, anna, bernd = anlage
    fach_nr = await modus.befuellen(anna.id, None)
    async with SessionFactory() as s:
        fach_id = await s.scalar(select(Fach.id).where(Fach.nummer == fach_nr))
    with pytest.raises(AblaufFehler, match="nicht frei"):
        await modus.befuellen(bernd.id, None, fach_id)


async def test_stornieren(anlage, db):
    modus, ueberwachung, schloss, anna, _ = anlage
    await modus.befuellen(anna.id, None)
    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    fach = await _fach(db, 2)

    await modus.stornieren(fach.id, None)
    assert (await _fach(db, 2)).zustand == "entnahme"
    assert schloss.verriegelt[1] is False  # zum Ausräumen geöffnet
    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    assert (await _fach(db, 2)).zustand == "frei"
    assert (await modus.chip("AA01"))["art"] == "kein_fach"


async def test_gesperrtes_fach(anlage, db):
    modus, ueberwachung, schloss, anna, _ = anlage
    await modus.befuellen(anna.id, None)
    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    fach = await _fach(db, 2)
    await modus.sperren(fach.id, True, None)
    assert (await modus.chip("AA01"))["art"] == "fach_gesperrt"
    assert schloss.verriegelt[1] is True
    # Befüllen überspringt gesperrte Fächer
    await modus.sperren(fach.id, False, None)


async def test_modul_aus_kein_zustandswechsel(anlage, db):
    modus, ueberwachung, schloss, anna, _ = anlage
    schloss.online = False
    with pytest.raises(AblaufFehler, match="Störung"):
        await modus.befuellen(anna.id, None)
    assert (await _fach(db, 2)).zustand == "frei"  # Kommunikation ≠ mechanisch
    assert await db.scalar(select(Zuweisung)) is None

    await ueberwachung.pruefen()
    assert set(ueberwachung.status.values()) == {"gestoert"}


async def test_klemmendes_schloss_wird_gestoert(anlage, db):
    modus, _, schloss, anna, _ = anlage

    async def klemmt(kanal, dauer_ms):
        schloss.impulse.append((kanal, dauer_ms))  # Impuls ja, Tür bleibt zu

    schloss.open = klemmt
    with pytest.raises(AblaufFehler):
        await modus.befuellen(anna.id, None)
    fach = await _fach(db, 2)
    assert fach.zustand == "gestoert"
    assert await db.scalar(select(Zuweisung)) is None

    assert await modus.stoerung_quittieren(fach.id, None) == "frei"


async def test_anlernen(anlage, db):
    modus, _, _, anna, _ = anlage
    assert (await modus.chip("CC03"))["art"] == "unbekannt"
    modus.anlernen_starten(None, anna.id)
    meldung = await modus.chip("CC03")
    assert meldung["art"] == "angelernt" and meldung["name"] == "Anna"
    chip = await db.scalar(select(Chip).where(Chip.kennung == "CC03"))
    assert chip.mitarbeiter_id == anna.id
    assert not modus.anlernen.aktiv  # genau ein Chip pro Vorgang


async def test_waesche_bekommt_menue(anlage, db):
    modus, _, _, _, bernd = anlage
    rolle = await db.scalar(select(Rolle).where(Rolle.name == "waesche"))
    db.add(Benutzer(login="b", rolle_id=rolle.id, mitarbeiter_id=bernd.id, aktiv=True))
    await db.commit()
    meldung = await modus.chip("BB02")
    assert meldung["art"] == "menue" and meldung["eigenes_fach"] is None


async def test_protokoll_vollstaendig(anlage, db):
    modus, ueberwachung, schloss, anna, _ = anlage
    await modus.befuellen(anna.id, None)
    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    await modus.chip("AA01")
    schloss.tuer_schliessen(1)
    await ueberwachung.pruefen()
    arten = list(await db.scalars(select(Ereignis.art).order_by(Ereignis.id)))
    assert arten == [
        "befuellung_begonnen",
        "fach_befuellt",
        "chip_gelesen",
        "abholung",
        "fach_frei",
    ]
