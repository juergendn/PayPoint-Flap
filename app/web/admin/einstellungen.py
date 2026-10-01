"""Einstellungen bearbeiten (nur Admin) und Systeminfo."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, text

from app.config import app_version
from app.core import einstellungen, mail
from app.core.protokoll import protokollieren
from app.db.models import Benutzer, Ereignis, Mail
from app.web.admin.hilfe import Session, seite, weiter
from app.web.auth import recht

router = APIRouter()
Admin = Annotated[Benutzer, Depends(recht("einstellungen_verwalten"))]


async def _systeminfo(request: Request, session) -> dict:
    db_groesse = await session.scalar(
        text("SELECT pg_size_pretty(pg_database_size(current_database()))")
    )
    anzahl, aeltester = (
        await session.execute(
            select(func.count(Ereignis.id), func.min(Ereignis.zeitpunkt))
        )
    ).one()
    return {
        "version": app_version(),
        "db_groesse": db_groesse,
        "ereignisse": anzahl,
        "aeltester": aeltester,
        "leser_ok": await request.app.state.leser_dienst.leser.health(),
        "mails": list(
            await session.scalars(select(Mail).order_by(Mail.id.desc()).limit(10))
        ),
        "mails_offen": await session.scalar(
            select(func.count(Mail.id)).where(Mail.status == "offen")
        ),
    }


def _gruppen() -> dict[str, list]:
    gruppen: dict[str, list] = {}
    for d in einstellungen.DEFINITIONEN:
        gruppen.setdefault(d.gruppe, []).append(d)
    return gruppen


@router.get("/einstellungen", response_class=HTMLResponse)
async def anzeigen(request: Request, session: Session, _: Admin):
    return seite(
        request,
        "admin/einstellungen.html",
        aktiv="einstellungen",
        gruppen=_gruppen(),
        werte=await einstellungen.alle(session),
        info=await _systeminfo(request, session),
    )


@router.post("/einstellungen")
async def speichern(request: Request, session: Session, benutzer: Admin):
    formular = {k: str(v) for k, v in (await request.form()).items()}
    geaendert, fehler = await einstellungen.speichern(session, formular)
    if fehler:
        await session.rollback()
        werte = await einstellungen.alle(session)
        # Eingaben stehen lassen, damit man nur den Fehler korrigiert
        werte.update({k: v for k, v in formular.items() if k in werte})
        return seite(
            request,
            "admin/einstellungen.html",
            status_code=400,
            aktiv="einstellungen",
            gruppen=_gruppen(),
            werte=werte,
            info=await _systeminfo(request, session),
            fehler=" · ".join(fehler),
        )
    if not geaendert:
        return weiter("/admin/einstellungen", "Keine Änderung")
    # Werte geheimer Felder nicht ins Protokoll
    protokollieren(
        session,
        "einstellungen_geaendert",
        benutzer_id=benutzer.id,
        schluessel=geaendert,
    )
    await session.commit()
    return weiter(
        "/admin/einstellungen", f"{len(geaendert)} Einstellung(en) gespeichert"
    )


@router.post("/einstellungen/testmail")
async def testmail(
    session: Session, benutzer: Admin, empfaenger: Annotated[str, Form()] = ""
):
    """Sofort senden statt einreihen – die Rückmeldung soll den echten
    SMTP-Fehler zeigen, nicht erst in der Queue landen."""
    empfaenger = empfaenger.strip() or await einstellungen.lesen(
        session, "mail.waesche"
    )
    if not empfaenger or "@" not in empfaenger:
        return weiter("/admin/einstellungen", fehler="Kein gültiger Empfänger")
    k = await mail.konfig(session)
    if k is None:
        return weiter(
            "/admin/einstellungen", fehler="SMTP-Server und Absender eintragen"
        )
    try:
        await mail.senden(
            k,
            empfaenger,
            "Klappenautomat: Testmail",
            "Diese Testmail bestätigt, dass der Klappenautomat Mails versenden kann.",
        )
    except Exception as e:
        return weiter(
            "/admin/einstellungen",
            fehler=f"Versand fehlgeschlagen: {type(e).__name__}: {e}",
        )
    protokollieren(session, "testmail", benutzer_id=benutzer.id, empfaenger=empfaenger)
    await session.commit()
    return weiter("/admin/einstellungen", f"Testmail an {empfaenger} gesendet")
