"""Anmeldung im Webinterface: Sitzungscookie, aktueller Benutzer, Rechteprüfung.

Nutzung in Routen:
    benutzer: Benutzer = Depends(recht("mitarbeiter_verwalten"))
"""

import time
from urllib.parse import quote, urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import auth, einstellungen
from app.db.models import Benutzer, Rolle
from app.db.session import get_session

COOKIE = "mvt_sitzung"
# Token nur erneuern, wenn das letzte älter als das ist – spart Set-Cookie bei
# jedem Polling-Aufruf.
ERNEUERN_NACH_S = 60


class NichtAngemeldet(Exception):
    pass


async def sitzungsdauer_s(session: AsyncSession) -> int:
    return 60 * await einstellungen.lesen_int(session, "web.sitzung_min", 30)


async def benutzer_laden(session: AsyncSession, benutzer_id: int) -> Benutzer | None:
    return await session.scalar(
        select(Benutzer)
        .where(Benutzer.id == benutzer_id)
        .options(
            selectinload(Benutzer.rolle).selectinload(Rolle.rechte),
            selectinload(Benutzer.mitarbeiter),
        )
    )


async def aktueller_benutzer_optional(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Benutzer | None:
    text = request.cookies.get(COOKIE)
    if not text:
        return None
    schluessel = await auth.geheimnis(session)
    token = auth.token_lesen(schluessel, text, await sitzungsdauer_s(session))
    if token is None:
        return None
    benutzer = await benutzer_laden(session, token.benutzer_id)
    if (
        benutzer is None
        or not benutzer.aktiv
        or token.passwort != auth.passwort_kennung(benutzer.passwort_hash)
    ):
        return None
    # Gleitende Sitzung: Aktivität verlängert, die Middleware setzt das Cookie.
    if time.time() - token.zeit > ERNEUERN_NACH_S:
        token.zeit = time.time()
        request.state.neues_token = auth.token_erstellen(schluessel, token)
    request.state.benutzer = benutzer
    # Für Templates als einfache Werte: bleiben gültig, auch wenn die Sitzung
    # später zurückgerollt wird und ORM-Objekte verfallen.
    request.state.rechte = benutzer.rechte
    request.state.kopf = {"login": benutzer.login, "rolle": benutzer.rolle.bezeichnung}
    return benutzer


async def aktueller_benutzer(
    benutzer: Benutzer | None = Depends(aktueller_benutzer_optional),
) -> Benutzer:
    if benutzer is None:
        raise NichtAngemeldet()
    return benutzer


def recht(schluessel: str):
    """Abhängigkeit: angemeldet und mit dem Recht `schluessel`, sonst 403."""

    async def pruefen(benutzer: Benutzer = Depends(aktueller_benutzer)) -> Benutzer:
        if schluessel not in benutzer.rechte:
            raise HTTPException(403, "Keine Berechtigung")
        return benutzer

    return pruefen


def anmelden(response: Response, schluessel: bytes, benutzer: Benutzer) -> None:
    token = auth.Token(
        benutzer.id, auth.passwort_kennung(benutzer.passwort_hash), time.time()
    )
    _cookie_setzen(response, auth.token_erstellen(schluessel, token))


def abmelden(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def _cookie_setzen(response: Response, wert: str) -> None:
    # Kein max_age: Sitzungscookie, Ablauf steuert der Zeitstempel im Token.
    # Kein Secure: im Automaten-LAN läuft HTTP (TLS über VPN).
    response.set_cookie(COOKIE, wert, httponly=True, samesite="strict", path="/")


async def nicht_angemeldet_behandeln(request: Request, _: Exception) -> Response:
    ziel = "/admin/login?weiter=" + quote(request.url.path)
    if request.headers.get("HX-Request"):
        # htmx folgt keinem 303 als Seitenwechsel – es braucht HX-Redirect.
        return Response(status_code=401, headers={"HX-Redirect": ziel})
    return RedirectResponse(ziel, status_code=303)


class SitzungsMiddleware(BaseHTTPMiddleware):
    """Setzt erneuerte Tokens und weist fremde Formular-POSTs ab (CSRF)."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            herkunft = request.headers.get("origin") or request.headers.get("referer")
            if herkunft and urlsplit(herkunft).netloc != request.headers.get("host"):
                return Response("Fremde Herkunft", status_code=403)
        response = await call_next(request)
        neues = getattr(request.state, "neues_token", None)
        if neues:
            _cookie_setzen(response, neues)
        return response
