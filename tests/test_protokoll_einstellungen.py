"""Protokoll (Filter, Export, Ortszeit) und Einstellungen (Prüfung, Rechte)."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.core import auth, einstellungen
from app.db.models import Benutzer, Einstellung, Ereignis, Fach, Mitarbeiter, Rolle


async def _ereignisse(db):
    db.add(Fach(id=50, automat_id=1, nummer=7, zustand="frei", gesperrt=False))
    db.add(Mitarbeiter(id=60, personalnummer="77", name="Paula Protokoll", aktiv=True))
    await db.flush()
    db.add_all(
        [
            # 22:30 UTC am 1.3. = 23:30 Ortszeit am 1.3.
            Ereignis(
                automat_id=1,
                art="abholung",
                fach_id=50,
                mitarbeiter_id=60,
                zeitpunkt=datetime(2026, 3, 1, 22, 30, tzinfo=UTC),
            ),
            # 23:30 UTC am 1.3. = 00:30 Ortszeit am 2.3.
            Ereignis(
                automat_id=1,
                art="stoerung",
                fach_id=50,
                details={"grund": "mechanik"},
                zeitpunkt=datetime(2026, 3, 1, 23, 30, tzinfo=UTC),
            ),
        ]
    )
    await db.commit()


async def test_protokoll_filter_und_ortszeit(admin_client, db):
    await _ereignisse(db)
    r = await admin_client.get("/admin/protokoll", params={"fach": "7"})
    assert r.status_code == 200 and "Paula Protokoll" in r.text
    assert "02.03.2026 00:30:00" in r.text  # Ortszeit, nicht UTC

    r = await admin_client.get(
        "/admin/protokoll",
        params={"von": "2026-03-02", "bis": "2026-03-02", "fach": "7"},
    )
    assert "<td>Störung</td>" in r.text and "Paula" not in r.text

    r = await admin_client.get("/admin/protokoll", params={"person": "paula"})
    assert "<td>Abholung</td>" in r.text and "<td>Störung</td>" not in r.text


async def test_protokoll_csv(admin_client, db):
    await _ereignisse(db)
    r = await admin_client.get("/admin/protokoll.csv", params={"fach": "7"})
    assert r.status_code == 200 and r.text.startswith("﻿Zeit;Ereignis")
    assert "grund: mechanik" in r.text


async def test_rechte_protokoll_einstellungen(client, db):
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
    assert (await client.get("/admin/protokoll")).status_code == 200
    assert (await client.get("/admin/einstellungen")).status_code == 403


def test_pruefen():
    d = einstellungen.NACH_SCHLUESSEL["schloss.impuls_ms"]
    assert einstellungen.pruefen(d, "1500") == ("1500", None)
    assert einstellungen.pruefen(d, "900")[1]  # unter Kerong-Minimum
    assert einstellungen.pruefen(d, "abc")[1]
    pw = einstellungen.NACH_SCHLUESSEL["smtp.passwort"]
    assert einstellungen.pruefen(pw, "") == (None, None)  # leer = unverändert


async def test_einstellungen_speichern(admin_client, db):
    werte = {
        "schloss.impuls_ms": "1800",
        "smtp.host": "mail.example.org",
        "smtp.passwort": "geheim",
    }
    r = await admin_client.post("/admin/einstellungen", data=werte)
    assert r.status_code == 303
    db.expire_all()
    assert (await db.get(Einstellung, "schloss.impuls_ms")).wert == "1800"
    assert (await db.get(Einstellung, "smtp.passwort")).wert == "geheim"
    ereignis = await db.scalar(
        select(Ereignis).where(Ereignis.art == "einstellungen_geaendert")
    )
    assert "geheim" not in str(ereignis.details)

    # Leeres Passwortfeld lässt das Passwort stehen; Fehler speichert nichts
    r = await admin_client.post(
        "/admin/einstellungen", data={"smtp.passwort": "", "schloss.impuls_ms": "500"}
    )
    assert r.status_code == 400 and "mindestens 1000" in r.text
    db.expire_all()
    assert (await db.get(Einstellung, "schloss.impuls_ms")).wert == "1800"
    assert (await db.get(Einstellung, "smtp.passwort")).wert == "geheim"
    # Seite zeigt das Passwort nie
    assert "geheim" not in (await admin_client.get("/admin/einstellungen")).text
