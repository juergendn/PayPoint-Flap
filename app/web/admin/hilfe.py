"""Gemeinsame Helfer der Admin-Seiten."""

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.web import templates

Session = Annotated[AsyncSession, Depends(get_session)]


def seite(request: Request, vorlage: str, status_code: int = 200, **kontext: Any):
    """Rendert eine Admin-Seite; Benutzer und Hinweis aus der Anfrage kommen
    automatisch in den Kontext (für Navigation und Meldungen)."""
    kontext.setdefault("kopf", getattr(request.state, "kopf", None))
    kontext.setdefault("rechte", getattr(request.state, "rechte", set()))
    kontext.setdefault("hinweis", request.query_params.get("hinweis"))
    kontext.setdefault("fehler", request.query_params.get("fehler"))
    return templates.TemplateResponse(
        request, vorlage, kontext, status_code=status_code
    )


def weiter(
    url: str, hinweis: str | None = None, fehler: str | None = None
) -> RedirectResponse:
    """Nach einem POST umleiten (kein doppeltes Absenden per F5); Meldung als
    Query-Parameter, die Seite zeigt sie an."""
    for name, text in (("hinweis", hinweis), ("fehler", fehler)):
        if text:
            url += ("&" if "?" in url else "?") + name + "=" + quote(text)
    return RedirectResponse(url, status_code=303)


def sicheres_ziel(ziel: str | None, standard: str = "/admin") -> str:
    """Nur Ziele im eigenen Admin-Bereich – kein offener Redirect."""
    if ziel and ziel.startswith("/admin") and not ziel.startswith("//"):
        return ziel
    return standard
