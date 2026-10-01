"""Login, Logout und Ersteinrichtung (erster Administrator)."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from app.core import auth
from app.core.protokoll import protokollieren
from app.db.models import Benutzer, Rolle
from app.web import auth as web_auth
from app.web.admin.hilfe import Session, seite, sicheres_ziel, weiter

router = APIRouter()


async def _gibt_benutzer(session) -> bool:
    return (await session.scalar(select(func.count(Benutzer.id)))) > 0


@router.get("/login", response_class=HTMLResponse)
async def login_seite(request: Request, session: Session, weiter_zu: str = ""):
    if not await _gibt_benutzer(session):
        return weiter("/admin/einrichten")
    return seite(
        request,
        "admin/login.html",
        weiter_zu=weiter_zu or request.query_params.get("weiter", ""),
    )


@router.post("/login")
async def login(
    request: Request,
    session: Session,
    login: Annotated[str, Form()],
    passwort: Annotated[str, Form()],
    weiter_zu: Annotated[str, Form()] = "",
):
    benutzer = await session.scalar(
        select(Benutzer).where(func.lower(Benutzer.login) == login.strip().lower())
    )
    if (
        benutzer is None
        or not benutzer.aktiv
        or not auth.passwort_pruefen(passwort, benutzer.passwort_hash)
    ):
        protokollieren(session, "anmeldung_fehlgeschlagen", login=login[:50])
        await session.commit()
        # Bremst Durchprobieren, ohne Konten zu sperren (Sperre wäre ein
        # einfacher Weg, den Betrieb zu stören).
        await asyncio.sleep(1)
        return seite(
            request,
            "admin/login.html",
            status_code=401,
            fehler="Anmeldung fehlgeschlagen",
            login=login,
            weiter_zu=weiter_zu,
        )
    protokollieren(session, "anmeldung", benutzer_id=benutzer.id)
    await session.commit()
    antwort = weiter(sicheres_ziel(weiter_zu))
    web_auth.anmelden(antwort, await auth.geheimnis(session), benutzer)
    return antwort


@router.post("/logout")
async def logout():
    antwort = weiter("/admin/login")
    web_auth.abmelden(antwort)
    return antwort


@router.get("/einrichten", response_class=HTMLResponse)
async def einrichten_seite(request: Request, session: Session):
    if await _gibt_benutzer(session):
        return weiter("/admin/login")
    return seite(request, "admin/einrichten.html")


@router.post("/einrichten")
async def einrichten(
    request: Request,
    session: Session,
    login: Annotated[str, Form()],
    passwort: Annotated[str, Form()],
    passwort2: Annotated[str, Form()],
):
    # Nur solange es keinen einzigen Benutzer gibt – danach ist die Seite zu.
    if await _gibt_benutzer(session):
        return weiter("/admin/login")
    fehler = auth.passwort_mangel(passwort)
    if passwort != passwort2:
        fehler = "Passwörter stimmen nicht überein"
    if not login.strip():
        fehler = "Login fehlt"
    if fehler:
        return seite(
            request,
            "admin/einrichten.html",
            status_code=400,
            fehler=fehler,
            login=login,
        )
    rolle = await session.scalar(select(Rolle).where(Rolle.name == "admin"))
    benutzer = Benutzer(
        login=login.strip(),
        passwort_hash=auth.passwort_hash(passwort),
        rolle_id=rolle.id,
        aktiv=True,
    )
    session.add(benutzer)
    await session.flush()
    protokollieren(
        session, "benutzer_angelegt", benutzer_id=benutzer.id, ersteinrichtung=True
    )
    await session.commit()
    antwort = weiter("/admin", "Administrator angelegt")
    web_auth.anmelden(antwort, await auth.geheimnis(session), benutzer)
    return antwort
