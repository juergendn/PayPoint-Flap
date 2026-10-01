"""Protokoll einsehen und exportieren (Admin, Wäsche)."""

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import aliased

from app.core.protokoll import ARTEN
from app.db.models import Benutzer, Ereignis, Fach, Mitarbeiter
from app.web import ORTSZEIT, ortszeit
from app.web.admin.hilfe import Session, seite
from app.web.auth import recht

router = APIRouter()
Berechtigt = Annotated[Benutzer, Depends(recht("protokoll_lesen"))]
PRO_SEITE = 100
MAX_EXPORT = 50_000


def _datum(text: str) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _abfrage(von: str, bis: str, art: str, fach: str, person: str) -> Select:
    handelnder = aliased(Benutzer)
    abfrage = (
        select(Ereignis, Fach.nummer, Mitarbeiter.name, handelnder.login)
        .outerjoin(Fach, Fach.id == Ereignis.fach_id)
        .outerjoin(Mitarbeiter, Mitarbeiter.id == Ereignis.mitarbeiter_id)
        .outerjoin(handelnder, handelnder.id == Ereignis.benutzer_id)
    )
    # Datumsfelder sind deutsche Kalendertage, gespeichert wird in UTC.
    if d := _datum(von):
        abfrage = abfrage.where(
            Ereignis.zeitpunkt >= datetime.combine(d, time.min, ORTSZEIT)
        )
    if d := _datum(bis):
        abfrage = abfrage.where(
            Ereignis.zeitpunkt
            < datetime.combine(d + timedelta(days=1), time.min, ORTSZEIT)
        )
    if art:
        abfrage = abfrage.where(Ereignis.art == art)
    if fach.strip().isdigit():
        abfrage = abfrage.where(Fach.nummer == int(fach))
    if person.strip():
        muster = f"%{person.strip()}%"
        abfrage = abfrage.where(
            or_(
                Mitarbeiter.name.ilike(muster),
                Mitarbeiter.personalnummer.ilike(muster),
                handelnder.login.ilike(muster),
            )
        )
    return abfrage


def _details(ereignis: Ereignis) -> str:
    return ", ".join(f"{k}: {v}" for k, v in (ereignis.details or {}).items())


@router.get("/protokoll", response_class=HTMLResponse)
async def protokoll(
    request: Request,
    session: Session,
    _: Berechtigt,
    von: str = "",
    bis: str = "",
    art: str = "",
    fach: str = "",
    person: str = "",
    seite_nr: int = 1,
):
    abfrage = _abfrage(von, bis, art, fach, person)
    gesamt = await session.scalar(select(func.count()).select_from(abfrage.subquery()))
    seite_nr = max(1, seite_nr)
    zeilen = (
        await session.execute(
            abfrage.order_by(Ereignis.id.desc())
            .offset((seite_nr - 1) * PRO_SEITE)
            .limit(PRO_SEITE)
        )
    ).all()
    vorhandene_arten = sorted(
        await session.scalars(select(Ereignis.art).distinct()),
        key=lambda a: ARTEN.get(a, a),
    )
    filter_ = {"von": von, "bis": bis, "art": art, "fach": fach, "person": person}
    return seite(
        request,
        "admin/protokoll.html",
        aktiv="protokoll",
        zeilen=zeilen,
        gesamt=gesamt,
        seite_nr=seite_nr,
        seiten=max(1, -(-gesamt // PRO_SEITE)),
        filter=filter_,
        arten=ARTEN,
        vorhandene_arten=vorhandene_arten,
        details=_details,
        # Filter als Query-String für Blättern und CSV-Export
        filter_url=urlencode({k: v for k, v in filter_.items() if v}),
    )


@router.get("/protokoll.csv")
async def export(
    session: Session,
    benutzer: Berechtigt,
    von: str = "",
    bis: str = "",
    art: str = "",
    fach: str = "",
    person: str = "",
):
    """CSV für Excel (Semikolon, UTF-8 mit BOM)."""
    zeilen = (
        await session.execute(
            _abfrage(von, bis, art, fach, person)
            .order_by(Ereignis.id.desc())
            .limit(MAX_EXPORT)
        )
    ).all()
    puffer = io.StringIO()
    puffer.write("﻿")
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(
        ["Zeit", "Ereignis", "Fach", "Mitarbeiter", "Benutzer", "Details"]
    )
    for e, fach_nr, ma_name, login in zeilen:
        schreiber.writerow(
            [
                ortszeit(e.zeitpunkt, "%d.%m.%Y %H:%M:%S"),
                ARTEN.get(e.art, e.art),
                fach_nr or "",
                ma_name or "",
                login or "",
                _details(e),
            ]
        )
    return Response(
        puffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="protokoll.csv"'},
    )
