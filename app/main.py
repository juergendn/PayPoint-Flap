"""Einstieg der Web-App: Treiber und Hintergrunddienste leben im Lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import get_settings
from app.db.models import IoModul
from app.db.session import SessionFactory, engine
from app.drivers import reader
from app.drivers.lock import SchlossRegistry
from app.modes.bekleidung.ablauf import Bekleidung
from app.services.hintergrund import Hintergrund
from app.services.leser import LeserDienst
from app.services.tuerkontakte import Tuerueberwachung
from app.web import auth as web_auth
from app.web.admin import (
    anmeldung,
    benutzer,
    chips,
    einstellungen,
    mitarbeiter,
    protokoll,
)
from app.web.admin import routes as admin
from app.web.display import routes as display
from app.web.display.sitzung import DisplaySitzungen

settings = get_settings()
logging.basicConfig(
    level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    schloesser = SchlossRegistry()
    async with SessionFactory() as session:
        module = await session.scalars(
            select(IoModul).where(IoModul.automat_id == settings.automat_id)
        )
        schloesser.laden(list(module))

    modus = Bekleidung(schloesser, SessionFactory)
    ueberwachung = Tuerueberwachung(schloesser, SessionFactory, modus)
    display_sitzungen = DisplaySitzungen()

    async def chip_verarbeiten(kennung: str) -> dict:
        return await display_sitzungen.chip_meldung(await modus.chip(kennung))

    leser_dienst = LeserDienst(reader.erzeuge(settings), chip_verarbeiten)
    hintergrund = Hintergrund(SessionFactory)
    ueberwachung.starten()
    leser_dienst.starten()
    hintergrund.starten()

    app.state.schloesser = schloesser
    app.state.modus = modus
    app.state.ueberwachung = ueberwachung
    app.state.leser_dienst = leser_dienst
    app.state.display = display_sitzungen
    app.state.hintergrund = hintergrund
    yield
    await hintergrund.stoppen()
    await leser_dienst.stoppen()
    await ueberwachung.stoppen()
    await schloesser.schliessen()
    await engine.dispose()


app = FastAPI(title="MVT-Klappenautomat", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)
app.add_middleware(web_auth.SitzungsMiddleware)
app.add_exception_handler(web_auth.NichtAngemeldet, web_auth.nicht_angemeldet_behandeln)
app.include_router(display.router)
for teil in (anmeldung, admin, mitarbeiter, chips, benutzer, protokoll, einstellungen):
    app.include_router(teil.router, prefix="/admin")
