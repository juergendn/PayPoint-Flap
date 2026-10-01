"""Anmeldung, Ersteinrichtung, Sitzung und Rechte."""

import time

from sqlalchemy import select

from app.core import auth
from app.db.models import Benutzer, Ereignis, Rolle


def test_passwort_hash():
    h = auth.passwort_hash("geheim123")
    assert auth.passwort_pruefen("geheim123", h)
    assert not auth.passwort_pruefen("falsch", h)
    assert not auth.passwort_pruefen("geheim123", None)
    assert not auth.passwort_pruefen("geheim123", "kaputt")


def test_token_signatur_und_ablauf():
    schluessel = b"x" * 32
    text = auth.token_erstellen(schluessel, auth.Token(7, "abc", time.time()))
    assert auth.token_lesen(schluessel, text, 60).benutzer_id == 7
    assert auth.token_lesen(b"y" * 32, text, 60) is None
    nutzlast, signatur = text.split(".")
    assert auth.token_lesen(schluessel, nutzlast + "x." + signatur, 60) is None
    alt = auth.token_erstellen(schluessel, auth.Token(7, "abc", time.time() - 120))
    assert auth.token_lesen(schluessel, alt, 60) is None


async def test_ohne_anmeldung_umleitung(client):
    r = await client.get("/admin/mitarbeiter")
    assert r.status_code == 303
    assert r.headers["location"].startswith("/admin/login")


async def test_htmx_ohne_anmeldung(client):
    r = await client.get("/admin/faecher", headers={"HX-Request": "true"})
    assert r.status_code == 401
    assert r.headers["HX-Redirect"].startswith("/admin/login")


async def test_ersteinrichtung_nur_ohne_benutzer(client, db):
    r = await client.get("/admin/login")
    assert r.headers["location"] == "/admin/einrichten"

    r = await client.post(
        "/admin/einrichten",
        data={"login": "admin", "passwort": "kurz", "passwort2": "kurz"},
    )
    assert r.status_code == 400

    daten = {"login": "admin", "passwort": "geheim123", "passwort2": "geheim123"}
    r = await client.post("/admin/einrichten", data=daten)
    assert r.status_code == 303 and "mvt_sitzung" in r.cookies
    benutzer = await db.scalar(select(Benutzer))
    assert benutzer.login == "admin"

    # Zweiter Versuch: Seite ist zu, kein weiterer Admin
    client.cookies.clear()
    r = await client.post("/admin/einrichten", data={**daten, "login": "boese"})
    assert r.headers["location"] == "/admin/login"
    assert len(list(await db.scalars(select(Benutzer)))) == 1


async def test_login_falsch_wird_protokolliert(admin_client, db):
    admin_client.cookies.clear()
    r = await admin_client.post(
        "/admin/login", data={"login": "chef", "passwort": "nein"}
    )
    assert r.status_code == 401
    arten = list(await db.scalars(select(Ereignis.art)))
    assert "anmeldung_fehlgeschlagen" in arten


async def test_login_kein_offener_redirect(admin_client):
    admin_client.cookies.clear()
    r = await admin_client.post(
        "/admin/login",
        data={
            "login": "chef",
            "passwort": "geheim123",
            "weiter_zu": "https://boese.example",
        },
    )
    assert r.headers["location"] == "/admin"


async def test_passwortwechsel_beendet_sitzungen(admin_client, db):
    assert (await admin_client.get("/admin/mitarbeiter")).status_code == 200
    benutzer = await db.scalar(select(Benutzer).where(Benutzer.login == "chef"))
    benutzer.passwort_hash = auth.passwort_hash("anders123")
    await db.commit()
    assert (await admin_client.get("/admin/mitarbeiter")).status_code == 303


async def test_waesche_darf_keine_mitarbeiter_verwalten(client, db):
    rolle = await db.scalar(select(Rolle).where(Rolle.name == "waesche"))
    db.add(
        Benutzer(
            login="w",
            passwort_hash=auth.passwort_hash("waesche12"),
            rolle_id=rolle.id,
            aktiv=True,
        )
    )
    await db.commit()
    await client.post("/admin/login", data={"login": "w", "passwort": "waesche12"})
    assert (await client.get("/admin/mitarbeiter")).status_code == 403
    assert (await client.get("/admin/benutzer")).status_code == 403
    assert (await client.get("/admin/chips")).status_code == 200


async def test_fremde_herkunft_abgewiesen(admin_client):
    r = await admin_client.post(
        "/admin/chips",
        data={"kennung": "AABBCCDD"},
        headers={"origin": "http://boese.example"},
    )
    assert r.status_code == 403


async def test_letzter_admin_bleibt(admin_client, db):
    chef = await db.scalar(select(Benutzer).where(Benutzer.login == "chef"))
    r = await admin_client.post(
        f"/admin/benutzer/{chef.id}", data={"rolle_id": 2, "aktiv": "true"}
    )
    assert r.status_code == 400
    await db.refresh(chef)
    assert chef.rolle_id == 1
