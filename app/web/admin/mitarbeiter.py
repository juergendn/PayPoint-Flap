"""Mitarbeiter verwalten inkl. CSV-Import (nur Admin)."""

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core import mitarbeiter as kern
from app.core.protokoll import protokollieren
from app.db.models import Benutzer, Mitarbeiter
from app.web.admin.hilfe import Session, seite, weiter
from app.web.auth import recht

router = APIRouter()
Admin = Annotated[Benutzer, Depends(recht("mitarbeiter_verwalten"))]
MAX_DATEI = 2 * 1024 * 1024


@router.get("/mitarbeiter", response_class=HTMLResponse)
async def liste(
    request: Request, session: Session, _: Admin, q: str = "", alle: bool = False
):
    abfrage = (
        select(Mitarbeiter)
        .options(selectinload(Mitarbeiter.chips))
        .order_by(Mitarbeiter.name)
        .limit(1000)
    )
    if not alle:
        abfrage = abfrage.where(Mitarbeiter.aktiv)
    if q.strip():
        muster = f"%{q.strip()}%"
        abfrage = abfrage.where(
            or_(
                Mitarbeiter.name.ilike(muster),
                Mitarbeiter.personalnummer.ilike(muster),
                Mitarbeiter.abteilung.ilike(muster),
            )
        )
    liste = list(await session.scalars(abfrage))
    gesamt = await session.scalar(
        select(func.count(Mitarbeiter.id)).where(Mitarbeiter.aktiv)
    )
    return seite(
        request,
        "admin/mitarbeiter_liste.html",
        aktiv="mitarbeiter",
        liste=liste,
        q=q,
        alle=alle,
        gesamt=gesamt,
    )


def _formular(request, mitarbeiter=None, fehler=None, status_code=200, **werte):
    return seite(
        request,
        "admin/mitarbeiter_form.html",
        status_code=status_code,
        aktiv="mitarbeiter",
        m=mitarbeiter,
        fehler=fehler,
        werte=werte,
    )


@router.get("/mitarbeiter/neu", response_class=HTMLResponse)
async def neu_seite(request: Request, _: Admin):
    return _formular(request)


async def _speichern(
    session,
    benutzer,
    m: Mitarbeiter | None,
    personalnummer,
    name,
    email,
    abteilung,
    aktiv,
):
    werte = dict(
        personalnummer=personalnummer.strip(),
        name=name.strip(),
        email=email.strip() or None,
        abteilung=abteilung.strip() or None,
    )
    if not werte["personalnummer"] or not werte["name"]:
        return None, "Personalnummer und Name sind Pflicht", werte
    if werte["email"] and "@" not in werte["email"]:
        return None, "E-Mail-Adresse ungültig", werte
    neu = m is None
    if neu:
        m = Mitarbeiter(aktiv=True)
        session.add(m)
    else:
        m.aktiv = aktiv
    for k, v in werte.items():
        setattr(m, k, v)
    try:
        # Savepoint statt Rollback: ein voller Rollback ließe auch den
        # angemeldeten Benutzer verfallen, den die Fehlerseite noch braucht.
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        return None, f"Personalnummer {werte['personalnummer']} gibt es schon", werte
    protokollieren(
        session,
        "mitarbeiter_angelegt" if neu else "mitarbeiter_geaendert",
        mitarbeiter_id=m.id,
        benutzer_id=benutzer.id,
    )
    await session.commit()
    return m, None, werte


@router.post("/mitarbeiter/neu")
async def neu(
    request: Request,
    session: Session,
    benutzer: Admin,
    personalnummer: Annotated[str, Form()],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
    abteilung: Annotated[str, Form()] = "",
):
    m, fehler, werte = await _speichern(
        session, benutzer, None, personalnummer, name, email, abteilung, True
    )
    if fehler:
        return _formular(request, fehler=fehler, status_code=400, **werte)
    return weiter(f"/admin/mitarbeiter/{m.id}", "Mitarbeiter angelegt")


async def _laden(session, mitarbeiter_id: int) -> Mitarbeiter:
    m = await session.get(
        Mitarbeiter, mitarbeiter_id, options=[selectinload(Mitarbeiter.chips)]
    )
    if m is None:
        raise HTTPException(404, "Mitarbeiter unbekannt")
    return m


@router.get("/mitarbeiter/import", response_class=HTMLResponse)
async def import_seite(request: Request, _: Admin):
    return seite(request, "admin/mitarbeiter_import.html", aktiv="mitarbeiter")


@router.post("/mitarbeiter/import", response_class=HTMLResponse)
async def import_vorschau(
    request: Request, session: Session, _: Admin, datei: UploadFile
):
    daten = await datei.read(MAX_DATEI + 1)
    if len(daten) > MAX_DATEI:
        return seite(
            request,
            "admin/mitarbeiter_import.html",
            status_code=400,
            aktiv="mitarbeiter",
            fehler="Datei größer als 2 MB",
        )
    ergebnis = kern.csv_lesen(daten)
    vorhanden = set(await session.scalars(select(Mitarbeiter.personalnummer)))
    neu = sum(1 for z in ergebnis.zeilen if z.personalnummer not in vorhanden)
    fehlen = len(vorhanden - {z.personalnummer for z in ergebnis.zeilen})
    return seite(
        request,
        "admin/mitarbeiter_import.html",
        aktiv="mitarbeiter",
        ergebnis=ergebnis,
        neu=neu,
        bekannt=len(ergebnis.zeilen) - neu,
        fehlen=fehlen,
        # Die Datei geht unverändert in den zweiten Schritt – kein Zwischenspeicher
        # auf dem Gerät nötig.
        daten_b64=base64.b64encode(daten).decode(),
    )


@router.post("/mitarbeiter/import/anwenden")
async def import_anwenden(
    session: Session,
    benutzer: Admin,
    daten_b64: Annotated[str, Form()],
    fehlende_deaktivieren: Annotated[bool, Form()] = False,
):
    ergebnis = kern.csv_lesen(base64.b64decode(daten_b64))
    if not ergebnis.zeilen:
        return weiter("/admin/mitarbeiter/import", "Keine gültigen Zeilen")
    bilanz = await kern.csv_anwenden(session, ergebnis.zeilen, fehlende_deaktivieren)
    protokollieren(
        session,
        "mitarbeiter_import",
        benutzer_id=benutzer.id,
        neu=bilanz.neu,
        geaendert=bilanz.geaendert,
        deaktiviert=bilanz.deaktiviert,
        fehler=len(ergebnis.fehler),
    )
    await session.commit()
    return weiter(
        "/admin/mitarbeiter",
        f"Import: {bilanz.neu} neu, {bilanz.geaendert} geändert, "
        f"{bilanz.unveraendert} unverändert, {bilanz.deaktiviert} deaktiviert",
    )


@router.get("/mitarbeiter/{mitarbeiter_id}", response_class=HTMLResponse)
async def bearbeiten_seite(
    request: Request, session: Session, _: Admin, mitarbeiter_id: int
):
    return _formular(request, await _laden(session, mitarbeiter_id))


@router.post("/mitarbeiter/{mitarbeiter_id}")
async def bearbeiten(
    request: Request,
    session: Session,
    benutzer: Admin,
    mitarbeiter_id: int,
    personalnummer: Annotated[str, Form()],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
    abteilung: Annotated[str, Form()] = "",
    aktiv: Annotated[bool, Form()] = False,
):
    m = await _laden(session, mitarbeiter_id)
    gespeichert, fehler, werte = await _speichern(
        session, benutzer, m, personalnummer, name, email, abteilung, aktiv
    )
    if fehler:
        return _formular(
            request,
            await _laden(session, mitarbeiter_id),
            fehler=fehler,
            status_code=400,
            **werte,
        )
    return weiter(f"/admin/mitarbeiter/{m.id}", "Gespeichert")
