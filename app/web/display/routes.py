"""Kiosk-Display (Panel WP10A). Bisher nur Startseite + Live-Chipanzeige."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.web import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def start(request: Request):
    return templates.TemplateResponse(request, "display/start.html")


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    """Server-Sent Events: jeder gelesene Chip sofort ans Display."""
    dienst = request.app.state.leser_dienst

    async def strom() -> AsyncIterator[str]:
        q = dienst.abonnieren()
        try:
            while not await request.is_disconnected():
                try:
                    meldung = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    # Kommentarzeile hält die Verbindung durch Proxys/Timeouts offen.
                    yield ": ping\n\n"
                    continue
                yield f"event: chip\ndata: {json.dumps(meldung)}\n\n"
        finally:
            dienst.abbestellen(q)

    return StreamingResponse(strom(), media_type="text/event-stream")
