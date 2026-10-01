"""Grundeinrichtung beim ersten Start: Automat, IO-Module, Fächer 2–20.

Idempotent (nur wenn noch kein Automat existiert) – läuft bei jedem Start mit,
auch im Container. Testmitarbeiter/-chips nur mit MVT_SEED_TESTDATEN=1.
Aufruf: python -m app.seed
"""

import asyncio

from sqlalchemy import select, text

from app.config import get_settings
from app.core.auth import passwort_hash
from app.db.models import Automat, Benutzer, Chip, Fach, IoModul, Mitarbeiter, Rolle
from app.db.session import SessionFactory, engine

# Fachbelegung (siehe CLAUDE.md): (erstes Fach, Anzahl) je Modul.
BELEGUNG = [(2, 8), (10, 8), (18, 3)]

# Dieselben Kennungen bietet der Hardware-Simulator als Schnellknöpfe an.
TESTMITARBEITER = [
    ("1001", "Anna Becker", "anna.becker@example.org", "Produktion", "04A1B2C3D4"),
    ("1002", "Bernd Schmitz", "bernd.schmitz@example.org", "Lager", "04A1B2C3D5"),
    ("1003", "Clara Wolf", "clara.wolf@example.org", "Wäscherei", "04A1B2C3D6"),
]


async def main() -> None:
    settings = get_settings()
    async with SessionFactory() as session:
        if await session.scalar(select(Automat.id).limit(1)) is not None:
            print("Seed: Daten vorhanden, nichts zu tun")
            return

        automat = Automat(
            id=settings.automat_id,
            name="Muster Aachen",
            modus="bekleidung",
            standort="Entwicklung",
        )
        session.add(automat)
        await session.flush()
        # automat_id ist fest konfiguriert → Sequenz nachziehen.
        await session.execute(
            text("SELECT setval('automat_id_seq', (SELECT max(id) FROM automat))")
        )

        # Im Simulator teilen sich die Module einen Host mit eigenem Port je
        # Modul, am Automaten hat jedes Modul eine eigene IP mit Port 502.
        adressen = [a.strip().rsplit(":", 1) for a in settings.seed_io.split(",")]
        if len(adressen) != len(BELEGUNG):
            raise SystemExit(f"MVT_SEED_IO braucht {len(BELEGUNG)} Adressen")
        for i, ((erstes_fach, anzahl), (host, port)) in enumerate(
            zip(BELEGUNG, adressen)
        ):
            modul = IoModul(
                automat_id=automat.id,
                name=f"#{i + 1}",
                treiber="waveshare_io8",
                adresse=host,
                port=int(port),
                unit_id=1,
            )
            session.add(modul)
            await session.flush()
            for kanal in range(1, anzahl + 1):
                session.add(
                    Fach(
                        automat_id=automat.id,
                        nummer=erstes_fach + kanal - 1,
                        io_modul_id=modul.id,
                        kanal=kanal,
                    )
                )

        for nr, name, email, abteilung, kennung in (
            TESTMITARBEITER if settings.seed_testdaten else []
        ):
            ma = Mitarbeiter(
                personalnummer=nr, name=name, email=email, abteilung=abteilung
            )
            session.add(ma)
            await session.flush()
            session.add(
                Chip(kennung=kennung, technologie="MIFARE", mitarbeiter_id=ma.id)
            )

        if settings.seed_testdaten:
            # Nur Entwicklung: feste Logins, damit man sich sofort anmelden kann.
            # Am Automaten gibt es keine Standardpasswörter – dort legt die
            # Ersteinrichtung (/admin/einrichten) den ersten Admin an.
            # waesche = Clara Wolf (Wäscherei): ihr Chip öffnet am Display das Menü.
            rollen = {r.name: r.id for r in await session.scalars(select(Rolle))}
            clara = await session.scalar(
                select(Mitarbeiter.id).where(Mitarbeiter.personalnummer == "1003")
            )
            for login, rolle, ma in (
                ("admin", "admin", None),
                ("waesche", "waesche", clara),
            ):
                session.add(
                    Benutzer(
                        login=login,
                        passwort_hash=passwort_hash(login),
                        rolle_id=rollen[rolle],
                        mitarbeiter_id=ma,
                        aktiv=True,
                    )
                )

        await session.commit()
        print(
            "Seed: Grundeinrichtung angelegt"
            + (" (mit Testdaten)" if settings.seed_testdaten else "")
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
