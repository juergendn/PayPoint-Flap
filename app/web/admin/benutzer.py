"""Benutzer des Webinterfaces verwalten (nur Admin)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core import auth
from app.core.protokoll import protokollieren
from app.db.models import Benutzer, Mitarbeiter, Rolle
from app.web.admin.hilfe import Session, seite, weiter
from app.web.auth import recht

router = APIRouter()
Admin = Annotated[Benutzer, Depends(recht("benutzer_verwalten"))]


async def _auswahl(session) -> dict:
    return {
        "rollen": list(await session.scalars(select(Rolle).order_by(Rolle.id))),
        "mitarbeiter": list(
            await session.scalars(
                select(Mitarbeiter).where(Mitarbeiter.aktiv).order_by(Mitarbeiter.name)
            )
        ),
    }


@router.get("/benutzer", response_class=HTMLResponse)
async def liste(request: Request, session: Session, _: Admin):
    liste = await session.scalars(
        select(Benutzer)
        .options(selectinload(Benutzer.rolle), selectinload(Benutzer.mitarbeiter))
        .order_by(Benutzer.login)
    )
    return seite(
        request, "admin/benutzer_liste.html", aktiv="benutzer", liste=list(liste)
    )


async def _formular(request, session, b=None, fehler=None, status_code=200, **werte):
    return seite(
        request,
        "admin/benutzer_form.html",
        status_code=status_code,
        aktiv="benutzer",
        b=b,
        fehler=fehler,
        werte=werte,
        **await _auswahl(session),
    )


@router.get("/benutzer/neu", response_class=HTMLResponse)
async def neu_seite(request: Request, session: Session, _: Admin):
    return await _formular(request, session)


async def _admins_ohne(session, benutzer_id: int | None) -> int:
    """Aktive Admins außer dem genannten – es muss immer einer bleiben."""
    abfrage = (
        select(func.count(Benutzer.id))
        .join(Benutzer.rolle)
        .where(Rolle.name == "admin", Benutzer.aktiv)
    )
    if benutzer_id is not None:
        abfrage = abfrage.where(Benutzer.id != benutzer_id)
    return await session.scalar(abfrage)


@router.post("/benutzer/neu")
async def neu(
    request: Request,
    session: Session,
    admin: Admin,
    login: Annotated[str, Form()],
    rolle_id: Annotated[int, Form()],
    passwort: Annotated[str, Form()] = "",
    mitarbeiter_id: Annotated[str, Form()] = "",
):
    werte = dict(login=login.strip(), rolle_id=rolle_id, mitarbeiter_id=mitarbeiter_id)
    # Ohne Passwort ist ein Benutzer nur per Chip am Display nutzbar (über den
    # verknüpften Mitarbeiter) – für die Wäscheabteilung der Normalfall.
    fehler = auth.passwort_mangel(passwort) if passwort else None
    if not werte["login"]:
        fehler = "Login fehlt"
    if fehler:
        return await _formular(
            request, session, fehler=fehler, status_code=400, **werte
        )
    b = Benutzer(
        login=werte["login"],
        rolle_id=rolle_id,
        aktiv=True,
        passwort_hash=auth.passwort_hash(passwort) if passwort else None,
        mitarbeiter_id=int(mitarbeiter_id) if mitarbeiter_id.isdigit() else None,
    )
    session.add(b)
    try:
        # Savepoint statt Rollback: ein voller Rollback ließe auch den
        # angemeldeten Benutzer verfallen, den die Fehlerseite noch braucht.
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        return await _formular(
            request,
            session,
            fehler=f"Login {werte['login']} gibt es schon",
            status_code=400,
            **werte,
        )
    protokollieren(session, "benutzer_angelegt", benutzer_id=admin.id, login=b.login)
    await session.commit()
    return weiter("/admin/benutzer", f"Benutzer {b.login} angelegt")


async def _laden(session, benutzer_id: int) -> Benutzer:
    b = await session.get(
        Benutzer,
        benutzer_id,
        options=[selectinload(Benutzer.rolle), selectinload(Benutzer.mitarbeiter)],
    )
    if b is None:
        raise HTTPException(404, "Benutzer unbekannt")
    return b


@router.get("/benutzer/{benutzer_id}", response_class=HTMLResponse)
async def bearbeiten_seite(
    request: Request, session: Session, _: Admin, benutzer_id: int
):
    return await _formular(request, session, await _laden(session, benutzer_id))


@router.post("/benutzer/{benutzer_id}")
async def bearbeiten(
    request: Request,
    session: Session,
    admin: Admin,
    benutzer_id: int,
    rolle_id: Annotated[int, Form()],
    passwort: Annotated[str, Form()] = "",
    mitarbeiter_id: Annotated[str, Form()] = "",
    aktiv: Annotated[bool, Form()] = False,
):
    b = await _laden(session, benutzer_id)
    rolle = await session.get(Rolle, rolle_id)
    fehler = None
    if rolle is None:
        fehler = "Rolle unbekannt"
    elif (not aktiv or rolle.name != "admin") and await _admins_ohne(
        session, b.id
    ) == 0:
        fehler = "Der letzte aktive Administrator kann nicht entzogen werden"
    elif passwort:
        fehler = auth.passwort_mangel(passwort)
    if fehler:
        return await _formular(request, session, b, fehler=fehler, status_code=400)

    b.rolle_id = rolle_id
    b.aktiv = aktiv
    b.mitarbeiter_id = int(mitarbeiter_id) if mitarbeiter_id.isdigit() else None
    if passwort:
        # Neues Passwort macht alle bestehenden Sitzungen ungültig (Token-Kennung).
        b.passwort_hash = auth.passwort_hash(passwort)
    protokollieren(
        session,
        "benutzer_geaendert",
        benutzer_id=admin.id,
        login=b.login,
        passwort_neu=bool(passwort),
    )
    await session.commit()
    return weiter("/admin/benutzer", f"Benutzer {b.login} gespeichert")
