"""Webinterface – Entwicklungsstand: Fachübersicht mit Testöffnung.

ACHTUNG: noch ohne Login (kommt in Meilenstein 3). Nur im isolierten Netz betreiben.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import faecher
from app.db.models import Fach
from app.db.session import get_session
from app.web import templates

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


async def _faecher_kontext(request: Request, session: AsyncSession) -> dict:
    liste = await faecher.alle(session)
    status = await faecher.schloss_status_alle(request.app.state.schloesser, liste)
    gesund = {f.io_modul_id: status[f.id] != "gestoert" for f in liste if f.io_modul_id}
    leser_ok = await request.app.state.leser_dienst.leser.health()
    return {"faecher": liste, "status": status, "module": gesund, "leser_ok": leser_ok}


@router.get("", response_class=HTMLResponse)
async def uebersicht(request: Request, session: Session):
    kontext = await _faecher_kontext(request, session)
    return templates.TemplateResponse(request, "admin/uebersicht.html", kontext)


@router.get("/faecher", response_class=HTMLResponse)
async def faecher_teil(request: Request, session: Session):
    kontext = await _faecher_kontext(request, session)
    return templates.TemplateResponse(request, "admin/_faecher.html", kontext)


@router.post("/fach/{fach_id}/oeffnen", response_class=HTMLResponse)
async def fach_oeffnen(fach_id: int, request: Request, session: Session):
    fach = await session.get(Fach, fach_id, options=[selectinload(Fach.io_modul)])
    if fach is None:
        raise HTTPException(404, "Fach unbekannt")
    ok = await faecher.oeffnen(session, request.app.state.schloesser, fach, "admin")
    kontext = await _faecher_kontext(request, session)
    kontext["meldung"] = (
        ("success", f"Fach {fach.nummer} geöffnet")
        if ok
        else ("error", f"Fach {fach.nummer}: Schloss/Modul antwortet nicht")
    )
    return templates.TemplateResponse(request, "admin/_faecher.html", kontext)
