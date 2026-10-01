"""Gemeinsame Fixtures: Testdatenbank, App-Client, Hardware-Simulator.

Die Tests laufen gegen eine eigene Datenbank `mvt_test` auf dem DB-Server der
Entwicklungsumgebung (docker compose run --rm app pytest). Sie wird pro Lauf neu
angelegt und per Alembic migriert – die Migrationen sind damit mitgetestet.
"""

import asyncio
import os

# Muss vor dem ersten Import von app.* stehen: Engine und Settings lesen die
# URL beim Import.
_BASIS_URL = os.environ.get(
    "MVT_DATABASE_URL", "postgresql+asyncpg://mvt:mvt@localhost:5432/mvt"
)
TEST_URL = _BASIS_URL.rsplit("/", 1)[0] + "/mvt_test"
os.environ["MVT_DATABASE_URL"] = TEST_URL
# Lifespan im Test ohne serielle Schnittstelle
os.environ["MVT_LESER_TREIBER"] = "simulator"

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402

from hwsim.anlage import Anlage
from hwsim.leser import LeserSim
from hwsim.modbus import ModbusSimServer


@pytest.fixture(scope="session")
async def datenbank():
    """Legt mvt_test neu an und migriert auf den aktuellen Stand."""
    from alembic import command
    from alembic.config import Config

    roh = TEST_URL.replace("postgresql+asyncpg", "postgresql")
    verwaltung = await asyncpg.connect(roh.rsplit("/", 1)[0] + "/postgres")
    await verwaltung.execute("DROP DATABASE IF EXISTS mvt_test WITH (FORCE)")
    await verwaltung.execute("CREATE DATABASE mvt_test")
    await verwaltung.close()
    # env.py ruft asyncio.run() auf – deshalb in einem eigenen Thread.
    await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
    yield


@pytest.fixture
async def db(datenbank):
    """Leert die fachlichen Tabellen vor jedem Test (Rollen/Rechte bleiben)."""
    from sqlalchemy import text

    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        await session.execute(
            text(
                "TRUNCATE ereignis, zuweisung, chip, benutzer, mitarbeiter, fach,"
                " io_modul, automat, mail RESTART IDENTITY CASCADE"
            )
        )
        # Wie nach der Grundeinrichtung: Protokoll braucht einen Automaten.
        from app.db.models import Automat

        session.add(Automat(id=1, name="Test", modus="bekleidung"))
        await session.commit()
        yield session


@pytest.fixture
async def client(db):
    """HTTP-Client gegen die App mit echtem Lifespan (Leser = Simulator)."""
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as c:
            yield c


@pytest.fixture
async def admin_client(client, db):
    """Client mit angemeldetem Administrator."""
    from sqlalchemy import select

    from app.core.auth import passwort_hash
    from app.db.models import Benutzer, Rolle

    rolle = await db.scalar(select(Rolle).where(Rolle.name == "admin"))
    db.add(
        Benutzer(
            login="chef",
            passwort_hash=passwort_hash("geheim123"),
            rolle_id=rolle.id,
            aktiv=True,
        )
    )
    await db.commit()
    r = await client.post(
        "/admin/login", data={"login": "chef", "passwort": "geheim123"}
    )
    assert r.status_code == 303
    return client


@pytest.fixture
async def sim_modul():
    """Ein simuliertes Waveshare-Modul; liefert (anlage, modul, port)."""
    anlage = Anlage(ports=[0], min_impuls_ms=1000, tuer_zu_nach_s=0)
    modul = anlage.module[0]
    server = await ModbusSimServer(anlage, modul).starten("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async def ticker():
        while True:
            anlage.tick()
            await asyncio.sleep(0.02)

    task = asyncio.create_task(ticker())
    yield anlage, modul, port
    task.cancel()
    server.close()
    await server.wait_closed()


@pytest.fixture
async def sim_leser():
    leser = LeserSim()
    server = await leser.starten("127.0.0.1", 0)
    yield leser, server.sockets[0].getsockname()[1]
    server.close()
