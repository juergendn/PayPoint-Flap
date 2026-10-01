"""Mitarbeiter, CSV-Import und Chips."""

import base64

from sqlalchemy import select

from app.core.mitarbeiter import csv_lesen, kennung_normalisieren
from app.db.models import Chip, Mitarbeiter


def test_csv_excel_format():
    daten = (
        "Personalnr;Name;E-Mail;Abteilung\r\n"
        "1001;Anna Müller;anna@example.org;Wäscherei\r\n"
        "1002;Bernd;;\r\n"
        ";ohne Nummer;;\r\n"
        "1001;doppelt;;\r\n"
        "1003;Clara;kein-at;\r\n"
    ).encode("cp1252")
    e = csv_lesen(daten)
    assert [z.personalnummer for z in e.zeilen] == ["1001", "1002"]
    assert e.zeilen[0].name == "Anna Müller"
    assert e.zeilen[1].email is None
    assert len(e.fehler) == 3


def test_csv_utf8_bom_komma():
    e = csv_lesen("﻿name,personalnummer\nZoë,7\n".encode())
    assert e.zeilen[0].name == "Zoë" and e.zeilen[0].personalnummer == "7"


def test_csv_kopf_fehlt():
    assert csv_lesen(b"a;b\n1;2\n").fehler


def test_kennung():
    assert kennung_normalisieren(" 04:a1:b2:c3 ") == "04A1B2C3"
    assert kennung_normalisieren("xyz") is None


async def test_import_ablauf(admin_client, db):
    db.add(Mitarbeiter(personalnummer="9", name="Alt", aktiv=True))
    db.add(Mitarbeiter(personalnummer="1", name="Falsch", aktiv=True))
    await db.commit()
    csv = "personalnummer;name\n1;Richtig\n2;Neu\n".encode()

    r = await admin_client.post(
        "/admin/mitarbeiter/import", files={"datei": ("m.csv", csv, "text/csv")}
    )
    assert r.status_code == 200 and "1 neu" in r.text
    # Vorschau ändert nichts
    assert len(list(await db.scalars(select(Mitarbeiter)))) == 2

    r = await admin_client.post(
        "/admin/mitarbeiter/import/anwenden",
        data={
            "daten_b64": base64.b64encode(csv).decode(),
            "fehlende_deaktivieren": "true",
        },
    )
    assert r.status_code == 303
    db.expire_all()
    stand = {m.personalnummer: m for m in await db.scalars(select(Mitarbeiter))}
    assert stand["1"].name == "Richtig"
    assert stand["2"].aktiv
    assert not stand["9"].aktiv  # deaktiviert, nicht gelöscht


async def test_mitarbeiter_anlegen_doppelt(admin_client):
    daten = {"personalnummer": "42", "name": "Erika"}
    assert (
        await admin_client.post("/admin/mitarbeiter/neu", data=daten)
    ).status_code == 303
    r = await admin_client.post("/admin/mitarbeiter/neu", data=daten)
    assert r.status_code == 400 and "gibt es schon" in r.text


async def test_chip_zuordnen_und_loesen(admin_client, db):
    m = Mitarbeiter(personalnummer="5", name="Paul", aktiv=True)
    db.add(m)
    await db.commit()
    r = await admin_client.post(
        "/admin/chips", data={"kennung": "de:ad:be:ef", "mitarbeiter_id": str(m.id)}
    )
    assert r.status_code == 303
    chip = await db.scalar(select(Chip))
    assert chip.kennung == "DEADBEEF" and chip.mitarbeiter_id == m.id

    r = await admin_client.post("/admin/chips", data={"kennung": "DEADBEEF"})
    assert "schon" in r.headers["location"]

    await admin_client.post(
        f"/admin/chips/{chip.id}/zuordnen", data={"mitarbeiter_id": ""}
    )
    await db.refresh(chip)
    assert chip.mitarbeiter_id is None
