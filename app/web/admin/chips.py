"""Chips im Webinterface anlegen, zuordnen, sperren (Admin + Wäsche).

Anlernen am Automaten (Chip vorhalten) kommt mit dem Display (Meilenstein 4/5)
und landet als Chip ohne Mitarbeiter hier in der Liste „nicht zugeordnet“.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.mitarbeiter import kennung_normalisieren
from app.core.protokoll import protokollieren
from app.db.models import Benutzer, Chip, Mitarbeiter
from app.web.admin.hilfe import Session, seite, sicheres_ziel, weiter
from app.web.auth import recht

router = APIRouter()
Berechtigt = Annotated[Benutzer, Depends(recht("chip_verknuepfen"))]


@router.get("/chips", response_class=HTMLResponse)
async def liste(
    request: Request, session: Session, _: Berechtigt, filter: str = "alle", q: str = ""
):
    abfrage = (
        select(Chip)
        .options(selectinload(Chip.mitarbeiter))
        .order_by(Chip.angelegt_am.desc())
    )
    if filter == "frei":
        abfrage = abfrage.where(Chip.mitarbeiter_id.is_(None))
    if q.strip():
        abfrage = abfrage.outerjoin(Chip.mitarbeiter).where(
            Chip.kennung.ilike(f"%{q.strip()}%")
            | Mitarbeiter.name.ilike(f"%{q.strip()}%")
        )
    chips = list(await session.scalars(abfrage.limit(1000)))
    mitarbeiter = list(
        await session.scalars(
            select(Mitarbeiter).where(Mitarbeiter.aktiv).order_by(Mitarbeiter.name)
        )
    )
    return seite(
        request,
        "admin/chips.html",
        aktiv="chips",
        chips=chips,
        mitarbeiter=mitarbeiter,
        filter=filter,
        q=q,
    )


def _mitarbeiter_id(text: str) -> int | None:
    return int(text) if text.strip().isdigit() else None


@router.post("/chips")
async def anlegen(
    session: Session,
    benutzer: Berechtigt,
    kennung: Annotated[str, Form()],
    mitarbeiter_id: Annotated[str, Form()] = "",
    technologie: Annotated[str, Form()] = "",
    zurueck: Annotated[str, Form()] = "",
):
    ziel = sicheres_ziel(zurueck, "/admin/chips")
    normal = kennung_normalisieren(kennung)
    if normal is None:
        return weiter(ziel, "Kennung ungültig (Hex, 4–64 Zeichen)")
    chip = Chip(
        kennung=normal,
        technologie=technologie.strip() or None,
        mitarbeiter_id=_mitarbeiter_id(mitarbeiter_id),
        aktiv=True,
    )
    session.add(chip)
    try:
        # Savepoint statt Rollback: ein voller Rollback ließe auch den
        # angemeldeten Benutzer verfallen, den die Fehlerseite noch braucht.
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        return weiter(ziel, f"Chip {normal} ist schon erfasst")
    protokollieren(
        session,
        "chip_angelegt",
        chip_id=chip.id,
        mitarbeiter_id=chip.mitarbeiter_id,
        benutzer_id=benutzer.id,
    )
    await session.commit()
    return weiter(ziel, f"Chip {normal} angelegt")


async def _chip(session, chip_id: int) -> Chip:
    chip = await session.get(Chip, chip_id)
    if chip is None:
        raise HTTPException(404, "Chip unbekannt")
    return chip


@router.post("/chips/{chip_id}/zuordnen")
async def zuordnen(
    session: Session,
    benutzer: Berechtigt,
    chip_id: int,
    mitarbeiter_id: Annotated[str, Form()] = "",
    zurueck: Annotated[str, Form()] = "",
):
    chip = await _chip(session, chip_id)
    chip.mitarbeiter_id = _mitarbeiter_id(mitarbeiter_id)
    protokollieren(
        session,
        "chip_zugeordnet" if chip.mitarbeiter_id else "chip_geloest",
        chip_id=chip.id,
        mitarbeiter_id=chip.mitarbeiter_id,
        benutzer_id=benutzer.id,
    )
    await session.commit()
    return weiter(
        sicheres_ziel(zurueck, "/admin/chips"), f"Chip {chip.kennung} gespeichert"
    )


@router.post("/chips/{chip_id}/aktiv")
async def aktiv_umschalten(
    session: Session,
    benutzer: Berechtigt,
    chip_id: int,
    zurueck: Annotated[str, Form()] = "",
):
    chip = await _chip(session, chip_id)
    chip.aktiv = not chip.aktiv
    protokollieren(
        session,
        "chip_freigegeben" if chip.aktiv else "chip_gesperrt",
        chip_id=chip.id,
        benutzer_id=benutzer.id,
    )
    await session.commit()
    return weiter(
        sicheres_ziel(zurueck, "/admin/chips"),
        f"Chip {chip.kennung} {'freigegeben' if chip.aktiv else 'gesperrt'}",
    )


@router.post("/chips/{chip_id}/loeschen")
async def loeschen(
    session: Session,
    benutzer: Berechtigt,
    chip_id: int,
    zurueck: Annotated[str, Form()] = "",
):
    chip = await _chip(session, chip_id)
    kennung = chip.kennung
    protokollieren(session, "chip_geloescht", benutzer_id=benutzer.id, kennung=kennung)
    await session.delete(chip)
    await session.commit()
    return weiter(sicheres_ziel(zurueck, "/admin/chips"), f"Chip {kennung} gelöscht")
