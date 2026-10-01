"""Display: Sitzung per Chip, Befüllen am Panel, Sitzungsende."""

import httpx
import pytest
from sqlalchemy import select

from app.db.models import Benutzer, Chip, Fach, IoModul, Mitarbeiter, Rolle


@pytest.fixture
async def panel(db):
    """Anlage mit Simulator-Schlössern; App erst danach starten, damit der
    Lifespan die Module lädt."""
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
    for nr in (2, 3):
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
    waesche = Mitarbeiter(personalnummer="900", name="Wanda Wäsche", aktiv=True)
    anna = Mitarbeiter(personalnummer="1001", name="Anna Becker", aktiv=True)
    db.add_all([waesche, anna])
    await db.flush()
    rolle = await db.scalar(select(Rolle).where(Rolle.name == "waesche"))
    db.add(
        Benutzer(
            login="wanda", rolle_id=rolle.id, mitarbeiter_id=waesche.id, aktiv=True
        )
    )
    db.add_all(
        [
            Chip(kennung="W900", mitarbeiter_id=waesche.id, aktiv=True),
            Chip(kennung="A1001", mitarbeiter_id=anna.id, aktiv=True),
        ]
    )
    await db.commit()
    anna_id = anna.id

    from app.main import app

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield app, c, anna_id


async def _anmelden(app) -> dict:
    meldung = await app.state.leser_dienst.chip("W900")
    assert meldung["art"] == "menue"
    return {"X-Display-Token": meldung["token"]}


async def test_menue_nur_mit_sitzung(panel):
    app, c, _ = panel
    assert (await c.get("/display/menue")).status_code == 401
    kopf = await _anmelden(app)
    r = await c.get("/display/menue", headers=kopf)
    assert r.status_code == 200 and "Befüllen" in r.text and "Wanda" in r.text
    assert (
        await c.get("/display/menue", headers={"X-Display-Token": "falsch"})
    ).status_code == 401


async def test_befuellen_am_display(panel):
    app, c, anna_id = panel
    kopf = await _anmelden(app)

    r = await c.get("/display/suche", params={"q": "100"}, headers=kopf)
    assert "Anna Becker" in r.text
    r = await c.get("/display/suche", params={"q": "anna"}, headers=kopf)
    assert "Anna Becker" in r.text

    r = await c.get(f"/display/befuellen/{anna_id}", headers=kopf)
    assert "Fach" in r.text and "2" in r.text
    r = await c.post(f"/display/befuellen/{anna_id}", headers=kopf)
    assert "ist offen" in r.text

    fach_id = await _fach_id(app, 2)
    r = await c.get(
        f"/display/fach/{fach_id}/warten", params={"zweck": "befuellen"}, headers=kopf
    )
    assert r.status_code == 204  # Tür noch offen → weiter warten

    schloss = next(iter(app.state.schloesser._treiber.values()))
    schloss.tuer_schliessen(1)
    await app.state.ueberwachung.pruefen()
    r = await c.get(
        f"/display/fach/{fach_id}/warten", params={"zweck": "befuellen"}, headers=kopf
    )
    assert "belegt" in r.text

    # Anna ist jetzt in der Suche als „hat Fach 2“ gesperrt
    r = await c.get("/display/suche", params={"q": "anna"}, headers=kopf)
    assert "hat Fach 2" in r.text


async def test_fremder_chip_beendet_sitzung(panel):
    app, c, _ = panel
    kopf = await _anmelden(app)
    meldung = await app.state.leser_dienst.chip("A1001")
    assert meldung["art"] == "kein_fach" and "token" not in meldung
    assert (await c.get("/display/menue", headers=kopf)).status_code == 401


async def test_beenden(panel):
    app, c, _ = panel
    kopf = await _anmelden(app)
    assert (await c.post("/display/ende", headers=kopf)).status_code == 200
    assert (await c.get("/display/menue", headers=kopf)).status_code == 401


async def test_display_seite_ohne_cdn(panel):
    _, c, _ = panel
    r = await c.get("/")
    assert r.status_code == 200
    assert (
        "http://" not in r.text.replace("http://test", "") and "https://" not in r.text
    )


async def _fach_id(app, nummer: int) -> int:
    from app.db.session import SessionFactory

    async with SessionFactory() as s:
        return await s.scalar(select(Fach.id).where(Fach.nummer == nummer))
