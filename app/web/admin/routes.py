"""Webinterface: Fachübersicht und Fach-Detail mit allen Aktionen des Modus.

Die Aktionen sind dieselben wie später am Display (Meilenstein 5) – beide rufen
nur den Modus auf.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core import faecher
from app.db.models import Benutzer, Ereignis, Fach, Mitarbeiter, Zuweisung
from app.modes.bekleidung.ablauf import AblaufFehler, offene_zuweisung
from app.web.admin.hilfe import Session, seite, weiter
from app.web.auth import aktueller_benutzer, recht

router = APIRouter()
Angemeldet = Annotated[Benutzer, Depends(aktueller_benutzer)]

ZUSTAND_TEXT = {
    "frei": "frei",
    "befuellung": "wird befüllt",
    "belegt": "belegt",
    "entnahme": "wird geleert",
    "gestoert": "gestört",
}


async def _belegung(session) -> dict[int, str]:
    """fach_id → Name des Mitarbeiters mit offener Zuweisung."""
    zeilen = await session.execute(
        select(Zuweisung.fach_id, Mitarbeiter.name)
        .join(Mitarbeiter, Mitarbeiter.id == Zuweisung.mitarbeiter_id)
        .where(offene_zuweisung())
    )
    return dict(zeilen.all())


async def _faecher_kontext(request: Request, session) -> dict:
    liste = await faecher.alle(session)
    status = request.app.state.ueberwachung.status
    if not status:  # erster Zyklus noch nicht durch
        status = await faecher.schloss_status_alle(request.app.state.schloesser, liste)
    gesund = {
        f.io_modul.name: status.get(f.id) != "gestoert" for f in liste if f.io_modul
    }
    leser_ok = await request.app.state.leser_dienst.leser.health()
    return {
        "faecher": liste,
        "status": status,
        "module": gesund,
        "leser_ok": leser_ok,
        "belegung": await _belegung(session),
        "zustand_text": ZUSTAND_TEXT,
    }


@router.get("", response_class=HTMLResponse)
async def uebersicht(request: Request, session: Session, _: Angemeldet):
    kontext = await _faecher_kontext(request, session)
    return seite(request, "admin/uebersicht.html", aktiv="uebersicht", **kontext)


@router.get("/faecher", response_class=HTMLResponse)
async def faecher_teil(request: Request, session: Session, _: Angemeldet):
    kontext = await _faecher_kontext(request, session)
    return seite(request, "admin/_faecher.html", **kontext)


@router.get("/fach/{fach_id}", response_class=HTMLResponse)
async def fach_detail(request: Request, session: Session, _: Angemeldet, fach_id: int):
    fach = await session.get(Fach, fach_id, options=[selectinload(Fach.io_modul)])
    if fach is None:
        raise HTTPException(404, "Fach unbekannt")
    zuweisung = await session.scalar(
        select(Zuweisung)
        .where(Zuweisung.fach_id == fach.id, offene_zuweisung())
        .options(selectinload(Zuweisung.mitarbeiter))
    )
    # Für „Befüllen“: nur aktive Mitarbeiter ohne offenes Fach.
    mit_fach = select(Zuweisung.mitarbeiter_id).where(offene_zuweisung())
    kandidaten = list(
        await session.scalars(
            select(Mitarbeiter)
            .where(Mitarbeiter.aktiv, Mitarbeiter.id.not_in(mit_fach))
            .order_by(Mitarbeiter.name)
        )
    )
    ereignisse = list(
        await session.scalars(
            select(Ereignis)
            .where(Ereignis.fach_id == fach.id)
            .order_by(Ereignis.id.desc())
            .limit(15)
        )
    )
    return seite(
        request,
        "admin/fach.html",
        aktiv="uebersicht",
        fach=fach,
        zuweisung=zuweisung,
        kandidaten=kandidaten,
        ereignisse=ereignisse,
        schloss=request.app.state.ueberwachung.status.get(fach.id, "unbekannt"),
        zustand_text=ZUSTAND_TEXT,
    )


async def _aktion(fach_id: int, aufruf, erfolg: str):
    try:
        ergebnis = await aufruf()
    except AblaufFehler as e:
        return weiter(f"/admin/fach/{fach_id}", fehler=str(e))
    return weiter(f"/admin/fach/{fach_id}", erfolg.format(ergebnis=ergebnis))


@router.post("/fach/{fach_id}/befuellen")
async def befuellen(
    request: Request,
    fach_id: int,
    benutzer: Annotated[Benutzer, Depends(recht("fach_befuellen"))],
    mitarbeiter_id: Annotated[int, Form()],
):
    modus = request.app.state.modus
    return await _aktion(
        fach_id,
        lambda: modus.befuellen(mitarbeiter_id, benutzer.id, fach_id),
        "Fach {ergebnis} geöffnet – einlegen und Tür schließen",
    )


@router.post("/fach/{fach_id}/stornieren")
async def stornieren(
    request: Request,
    fach_id: int,
    benutzer: Annotated[Benutzer, Depends(recht("zuweisung_stornieren"))],
):
    modus = request.app.state.modus
    return await _aktion(
        fach_id,
        lambda: modus.stornieren(fach_id, benutzer.id),
        "Zuweisung storniert – Fach {ergebnis} ausräumen und Tür schließen",
    )


@router.post("/fach/{fach_id}/sperren")
async def sperren(
    request: Request,
    fach_id: int,
    benutzer: Annotated[Benutzer, Depends(recht("fach_sperren"))],
    gesperrt: Annotated[bool, Form()] = False,
):
    modus = request.app.state.modus
    return await _aktion(
        fach_id,
        lambda: modus.sperren(fach_id, gesperrt, benutzer.id),
        "Fach gesperrt" if gesperrt else "Fach entsperrt",
    )


@router.post("/fach/{fach_id}/quittieren")
async def quittieren(
    request: Request,
    fach_id: int,
    benutzer: Annotated[Benutzer, Depends(recht("fach_sperren"))],
):
    modus = request.app.state.modus
    return await _aktion(
        fach_id,
        lambda: modus.stoerung_quittieren(fach_id, benutzer.id),
        "Störung quittiert – Fach ist jetzt {ergebnis}",
    )


@router.post("/fach/{fach_id}/oeffnen", response_class=HTMLResponse)
async def fach_oeffnen(
    fach_id: int,
    request: Request,
    session: Session,
    benutzer: Annotated[Benutzer, Depends(recht("fach_oeffnen"))],
):
    """Öffnen ohne Zustandswechsel. Aus der Übersicht (htmx) kommt das Raster
    zurück, von der Detailseite eine Umleitung."""
    try:
        nummer = await request.app.state.modus.oeffnen_manuell(fach_id, benutzer.id)
        meldung = ("success", f"Fach {nummer} geöffnet")
    except AblaufFehler as e:
        meldung = ("error", str(e))
    if not request.headers.get("HX-Request"):
        art, text = meldung
        return weiter(
            f"/admin/fach/{fach_id}",
            hinweis=text if art == "success" else None,
            fehler=text if art == "error" else None,
        )
    kontext = await _faecher_kontext(request, session)
    return seite(request, "admin/_faecher.html", meldung=meldung, **kontext)
