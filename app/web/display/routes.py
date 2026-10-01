"""Kiosk-Display (Panel WP10A, 1280×800, Touch).

Die Seite `/` ist eine Hülle; jeder Bildschirm ist ein HTMX-Fragment, das in
`#bildschirm` getauscht wird. Aktionen brauchen eine Display-Sitzung (Chip der
Wäscheabteilung) – siehe sitzung.py.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core import einstellungen
from app.core.faecher import ZUSTAND_TEXT
from app.db.models import Fach, Mitarbeiter, Zuweisung
from app.db.session import SessionFactory
from app.modes.bekleidung.ablauf import AblaufFehler, offene_zuweisung
from app.web import templates
from app.web.display.sitzung import DisplaySitzung

router = APIRouter()
MAX_TREFFER = 12


def sitzung(request: Request) -> DisplaySitzung:
    s = request.app.state.display.pruefen(request.headers.get("X-Display-Token"))
    if s is None:
        # 401 → display.js kehrt zur Startseite zurück
        raise HTTPException(401, "Display-Sitzung abgelaufen")
    return s


Sitzung = Annotated[DisplaySitzung, Depends(sitzung)]


def _recht(s: DisplaySitzung, schluessel: str) -> None:
    if schluessel not in s.rechte:
        raise HTTPException(403, "Keine Berechtigung")


def fragment(request: Request, vorlage: str, **kontext) -> HTMLResponse:
    return templates.TemplateResponse(request, f"display/{vorlage}", kontext)


def meldung(
    request: Request,
    art: str,
    text: str,
    s: DisplaySitzung | None = None,
    weiter: str | None = None,
):
    """Ergebnis-Bildschirm; `weiter` = nächster Bildschirm nach kurzer Zeit."""
    return fragment(request, "_meldung.html", art=art, text=text, s=s, weiter=weiter)


# ---------- Hülle und Live-Ereignisse ----------


@router.get("/", response_class=HTMLResponse)
async def start(request: Request):
    async with SessionFactory() as session:
        timeout_s = await einstellungen.lesen_int(session, "display.timeout_s", 60)
    return templates.TemplateResponse(
        request, "display/start.html", {"timeout_s": timeout_s}
    )


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    """Server-Sent Events: jeder gelesene Chip sofort ans Display."""
    dienst = request.app.state.leser_dienst

    async def strom() -> AsyncIterator[str]:
        q = dienst.abonnieren()
        try:
            while not await request.is_disconnected():
                try:
                    m = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    # Kommentarzeile hält die Verbindung durch Proxys/Timeouts offen.
                    yield ": ping\n\n"
                    continue
                yield f"event: chip\ndata: {json.dumps(m)}\n\n"
        finally:
            dienst.abbestellen(q)

    return StreamingResponse(strom(), media_type="text/event-stream")


@router.get("/display/start", response_class=HTMLResponse)
async def leerlauf(request: Request):
    return fragment(request, "_start.html")


@router.post("/display/ende", response_class=HTMLResponse)
async def ende(request: Request):
    request.app.state.display.beenden()
    return fragment(request, "_start.html")


# ---------- Menü ----------


@router.get("/display/menue", response_class=HTMLResponse)
async def menue(request: Request, s: Sitzung):
    async with SessionFactory() as session:
        eigenes = await session.scalar(
            select(Fach.nummer)
            .join(Zuweisung, Zuweisung.fach_id == Fach.id)
            .where(Zuweisung.mitarbeiter_id == s.mitarbeiter_id, offene_zuweisung())
        )
    return fragment(request, "_menue.html", s=s, eigenes_fach=eigenes)


@router.post("/display/abholen", response_class=HTMLResponse)
async def abholen(request: Request, s: Sitzung):
    m = await request.app.state.modus.abholen(s.mitarbeiter_id)
    if m["art"] == "abholung":
        return meldung(
            request, "ok", f"Fach {m['fach']} ist offen", s, "/display/menue"
        )
    return meldung(
        request, "fehler", m.get("text", "Kein Fach bereit"), s, "/display/menue"
    )


# ---------- Befüllen ----------


@router.get("/display/befuellen", response_class=HTMLResponse)
async def befuellen_suche(request: Request, s: Sitzung, zweck: str = "befuellen"):
    _recht(s, "fach_befuellen" if zweck == "befuellen" else "chip_anlernen")
    return fragment(request, "_suche.html", s=s, zweck=zweck)


@router.get("/display/suche", response_class=HTMLResponse)
async def suche(request: Request, s: Sitzung, q: str = "", zweck: str = "befuellen"):
    """Treffer zur Eingabe: Ziffern → Personalnummer (Anfang), sonst Name."""
    q = q.strip()
    treffer, belegt = [], {}
    if q:
        bedingung = (
            Mitarbeiter.personalnummer.startswith(q)
            if q.isdigit()
            else or_(*(Mitarbeiter.name.ilike(f"%{teil}%") for teil in q.split()))
        )
        async with SessionFactory() as session:
            treffer = list(
                await session.scalars(
                    select(Mitarbeiter)
                    .where(Mitarbeiter.aktiv, bedingung)
                    .order_by(Mitarbeiter.name)
                    .limit(MAX_TREFFER)
                )
            )
            belegt = dict(
                (
                    await session.execute(
                        select(Zuweisung.mitarbeiter_id, Fach.nummer)
                        .join(Fach, Fach.id == Zuweisung.fach_id)
                        .where(offene_zuweisung())
                    )
                ).all()
            )
    return fragment(
        request, "_treffer.html", treffer=treffer, belegt=belegt, q=q, zweck=zweck
    )


@router.get("/display/befuellen/{mitarbeiter_id}", response_class=HTMLResponse)
async def befuellen_bestaetigen(request: Request, s: Sitzung, mitarbeiter_id: int):
    _recht(s, "fach_befuellen")
    async with SessionFactory() as session:
        ma = await session.get(Mitarbeiter, mitarbeiter_id)
        fach = await request.app.state.modus.freies_fach(session)
    if ma is None:
        return meldung(
            request, "fehler", "Mitarbeiter unbekannt", s, "/display/befuellen"
        )
    if fach is None:
        return meldung(request, "fehler", "Kein freies Fach", s, "/display/menue")
    return fragment(request, "_bestaetigen.html", s=s, ma=ma, fach_nummer=fach.nummer)


@router.post("/display/befuellen/{mitarbeiter_id}", response_class=HTMLResponse)
async def befuellen(request: Request, s: Sitzung, mitarbeiter_id: int):
    _recht(s, "fach_befuellen")
    try:
        nummer = await request.app.state.modus.befuellen(mitarbeiter_id, s.benutzer_id)
    except AblaufFehler as e:
        return meldung(request, "fehler", str(e), s, "/display/menue")
    async with SessionFactory() as session:
        fach_id = await session.scalar(select(Fach.id).where(Fach.nummer == nummer))
        ma = await session.get(Mitarbeiter, mitarbeiter_id)
    return fragment(
        request,
        "_warten.html",
        s=s,
        fach_id=fach_id,
        nummer=nummer,
        name=ma.name,
        zweck="befuellen",
    )


@router.get("/display/fach/{fach_id}/warten", response_class=HTMLResponse)
async def warten(request: Request, s: Sitzung, fach_id: int, zweck: str):
    """Pollt, bis die Tür zu ist; dann Erfolg (Polling endet mit dem Tausch)."""
    async with SessionFactory() as session:
        fach = await session.get(Fach, fach_id)
    if fach.zustand in ("befuellung", "entnahme"):
        return Response(status_code=204)  # htmx: nichts tauschen, weiter pollen
    if zweck == "befuellen" and fach.zustand == "belegt":
        return fragment(request, "_befuellt.html", s=s, nummer=fach.nummer)
    return meldung(
        request,
        "ok",
        f"Fach {fach.nummer} ist {ZUSTAND_TEXT[fach.zustand]}",
        s,
        "/display/menue",
    )


# ---------- Fächer (öffnen, sperren, stornieren) ----------


@router.get("/display/faecher", response_class=HTMLResponse)
async def faecher_raster(request: Request, s: Sitzung):
    async with SessionFactory() as session:
        liste = list(
            await session.scalars(
                select(Fach).where(Fach.io_modul_id.is_not(None)).order_by(Fach.nummer)
            )
        )
        namen = dict(
            (
                await session.execute(
                    select(Zuweisung.fach_id, Mitarbeiter.name)
                    .join(Mitarbeiter, Mitarbeiter.id == Zuweisung.mitarbeiter_id)
                    .where(offene_zuweisung())
                )
            ).all()
        )
    return fragment(
        request,
        "_faecher.html",
        s=s,
        faecher=liste,
        namen=namen,
        status=request.app.state.ueberwachung.status,
        zustand_text=ZUSTAND_TEXT,
    )


@router.get("/display/fach/{fach_id}", response_class=HTMLResponse)
async def fach(request: Request, s: Sitzung, fach_id: int):
    async with SessionFactory() as session:
        f = await session.get(Fach, fach_id)
        zuweisung = await session.scalar(
            select(Zuweisung)
            .where(Zuweisung.fach_id == fach_id, offene_zuweisung())
            .options(selectinload(Zuweisung.mitarbeiter))
        )
    if f is None:
        return meldung(request, "fehler", "Fach unbekannt", s, "/display/faecher")
    return fragment(
        request,
        "_fach.html",
        s=s,
        fach=f,
        zuweisung=zuweisung,
        zustand_text=ZUSTAND_TEXT,
    )


@router.post("/display/fach/{fach_id}/{aktion}", response_class=HTMLResponse)
async def fach_aktion(request: Request, s: Sitzung, fach_id: int, aktion: str):
    modus = request.app.state.modus
    try:
        if aktion == "oeffnen":
            _recht(s, "fach_oeffnen")
            nr = await modus.oeffnen_manuell(fach_id, s.benutzer_id)
            return meldung(request, "ok", f"Fach {nr} ist offen", s, "/display/faecher")
        if aktion in ("sperren", "entsperren"):
            _recht(s, "fach_sperren")
            await modus.sperren(fach_id, aktion == "sperren", s.benutzer_id)
            text = "Fach gesperrt" if aktion == "sperren" else "Fach entsperrt"
            return meldung(request, "ok", text, s, f"/display/fach/{fach_id}")
        if aktion == "stornieren":
            _recht(s, "zuweisung_stornieren")
            nr = await modus.stornieren(fach_id, s.benutzer_id)
            return fragment(
                request,
                "_warten.html",
                s=s,
                fach_id=fach_id,
                nummer=nr,
                name=None,
                zweck="stornieren",
            )
    except AblaufFehler as e:
        return meldung(request, "fehler", str(e), s, "/display/faecher")
    raise HTTPException(404)


# ---------- Anlernen ----------


@router.post("/display/anlernen", response_class=HTMLResponse)
async def anlernen(
    request: Request, s: Sitzung, mitarbeiter_id: Annotated[str, Form()] = ""
):
    _recht(s, "chip_anlernen")
    ma_id = int(mitarbeiter_id) if mitarbeiter_id.isdigit() else None
    name = None
    if ma_id:
        async with SessionFactory() as session:
            ma = await session.get(Mitarbeiter, ma_id)
            name = ma.name if ma else None
    request.app.state.modus.anlernen_starten(s.benutzer_id, ma_id)
    return fragment(
        request,
        "_anlernen.html",
        s=s,
        name=name,
        sekunden=request.app.state.modus.anlernen.rest_s,
    )
