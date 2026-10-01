"""Datenmodell (SQLAlchemy 2).

Jede Tabelle mit Gerätebezug trägt `automat_id`, damit mehrere Automaten später in
eine zentrale Datenbank zusammengeführt werden können, ohne das Schema umzubauen.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# befuellung/entnahme: Tür ist offen, der Wechsel auf belegt/frei passiert erst,
# wenn der Türkontakt „zu“ meldet (Entscheidung 01.10.2026).
FACH_ZUSTAENDE = ("frei", "befuellung", "belegt", "entnahme", "gestoert")
MODI = ("bekleidung", "werkzeug")


class Base(DeclarativeBase):
    pass


class Automat(Base):
    __tablename__ = "automat"
    __table_args__ = (CheckConstraint(f"modus IN {MODI}", name="ck_automat_modus"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    modus: Mapped[str] = mapped_column(String(20), default="bekleidung")
    standort: Mapped[str | None] = mapped_column(String(200))


class IoModul(Base):
    """Ein IO-Modul bzw. Gateway; `treiber` wählt die Implementierung in drivers/lock."""

    __tablename__ = "io_modul"

    id: Mapped[int] = mapped_column(primary_key=True)
    automat_id: Mapped[int] = mapped_column(ForeignKey("automat.id"))
    name: Mapped[str] = mapped_column(String(50))
    treiber: Mapped[str] = mapped_column(String(30))
    adresse: Mapped[str] = mapped_column(String(100))
    port: Mapped[int] = mapped_column(Integer, default=502)
    unit_id: Mapped[int] = mapped_column(Integer, default=1)
    # Ob der Schlossschalter als Öffner oder Schließer verdrahtet ist, ist noch
    # offen (Muster) – deshalb pro Modul umschaltbar statt im Treiber fest.
    di_invertiert: Mapped[bool] = mapped_column(Boolean, default=False)


class Fach(Base):
    __tablename__ = "fach"
    __table_args__ = (
        UniqueConstraint("automat_id", "nummer"),
        UniqueConstraint("io_modul_id", "kanal"),
        CheckConstraint(f"zustand IN {FACH_ZUSTAENDE}", name="ck_fach_zustand"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automat_id: Mapped[int] = mapped_column(ForeignKey("automat.id"))
    nummer: Mapped[int] = mapped_column(Integer)
    io_modul_id: Mapped[int | None] = mapped_column(ForeignKey("io_modul.id"))
    kanal: Mapped[int | None] = mapped_column(Integer)
    zustand: Mapped[str] = mapped_column(String(20), default="frei")
    # Sperre ist unabhängig vom Zustand: ein belegtes Fach kann gesperrt werden,
    # ohne dass die Zuweisung verloren geht.
    gesperrt: Mapped[bool] = mapped_column(Boolean, default=False)

    io_modul: Mapped[IoModul | None] = relationship()


class Mitarbeiter(Base):
    __tablename__ = "mitarbeiter"

    id: Mapped[int] = mapped_column(primary_key=True)
    personalnummer: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(200))
    abteilung: Mapped[str | None] = mapped_column(String(100))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)

    chips: Mapped[list["Chip"]] = relationship(
        back_populates="mitarbeiter", order_by="Chip.id"
    )


class Chip(Base):
    __tablename__ = "chip"

    id: Mapped[int] = mapped_column(primary_key=True)
    kennung: Mapped[str] = mapped_column(String(64), unique=True)
    technologie: Mapped[str | None] = mapped_column(String(30))
    # NULL = am Automaten angelernt, aber noch keinem Mitarbeiter zugeordnet.
    mitarbeiter_id: Mapped[int | None] = mapped_column(
        ForeignKey("mitarbeiter.id", ondelete="SET NULL")
    )
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    angelegt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    mitarbeiter: Mapped[Mitarbeiter | None] = relationship(back_populates="chips")


rolle_recht = Table(
    "rolle_recht",
    Base.metadata,
    Column("rolle_id", ForeignKey("rolle.id", ondelete="CASCADE"), primary_key=True),
    Column("recht_id", ForeignKey("recht.id", ondelete="CASCADE"), primary_key=True),
)


class Rolle(Base):
    __tablename__ = "rolle"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    bezeichnung: Mapped[str] = mapped_column(String(100))

    rechte: Mapped[list["Recht"]] = relationship(secondary=rolle_recht)


class Recht(Base):
    __tablename__ = "recht"

    id: Mapped[int] = mapped_column(primary_key=True)
    schluessel: Mapped[str] = mapped_column(String(50), unique=True)
    beschreibung: Mapped[str] = mapped_column(String(200))


class Benutzer(Base):
    __tablename__ = "benutzer"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(50), unique=True)
    passwort_hash: Mapped[str | None] = mapped_column(String(255))
    rolle_id: Mapped[int] = mapped_column(ForeignKey("rolle.id"))
    mitarbeiter_id: Mapped[int | None] = mapped_column(
        ForeignKey("mitarbeiter.id", ondelete="SET NULL")
    )
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)

    rolle: Mapped[Rolle] = relationship()
    mitarbeiter: Mapped[Mitarbeiter | None] = relationship()

    @property
    def rechte(self) -> set[str]:
        """Rechte-Schlüssel der Rolle; setzt geladene `rolle.rechte` voraus."""
        return {r.schluessel for r in self.rolle.rechte}


class Zuweisung(Base):
    __tablename__ = "zuweisung"
    __table_args__ = (
        # Harte Regel aus dem Lastenheft: höchstens eine offene Zuweisung pro
        # Mitarbeiter – in der DB, damit auch parallele Anfragen sie nicht brechen.
        Index(
            "uq_zuweisung_offen_mitarbeiter",
            "mitarbeiter_id",
            unique=True,
            postgresql_where=text("abgeholt_am IS NULL AND NOT storniert"),
        ),
        # Ebenso kann ein Fach nur einen offenen Inhalt haben.
        Index(
            "uq_zuweisung_offen_fach",
            "fach_id",
            unique=True,
            postgresql_where=text("abgeholt_am IS NULL AND NOT storniert"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fach_id: Mapped[int] = mapped_column(ForeignKey("fach.id"))
    mitarbeiter_id: Mapped[int] = mapped_column(ForeignKey("mitarbeiter.id"))
    befuellt_von: Mapped[int | None] = mapped_column(
        ForeignKey("benutzer.id", ondelete="SET NULL")
    )
    befuellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    abgeholt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storniert: Mapped[bool] = mapped_column(Boolean, default=False)
    # Wäscheabteilung wurde an dieses Fach erinnert (nur einmal je Zuweisung)
    erinnert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fach: Mapped[Fach] = relationship()
    mitarbeiter: Mapped[Mitarbeiter] = relationship()


class Ereignis(Base):
    """Protokoll (Ringspeicher, 60 Tage). Fremdschlüssel mit SET NULL, damit das
    Löschen von Stammdaten das Protokoll nicht blockiert."""

    __tablename__ = "ereignis"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    zeitpunkt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    automat_id: Mapped[int] = mapped_column(ForeignKey("automat.id"))
    art: Mapped[str] = mapped_column(String(40))
    fach_id: Mapped[int | None] = mapped_column(
        ForeignKey("fach.id", ondelete="SET NULL")
    )
    chip_id: Mapped[int | None] = mapped_column(
        ForeignKey("chip.id", ondelete="SET NULL")
    )
    mitarbeiter_id: Mapped[int | None] = mapped_column(
        ForeignKey("mitarbeiter.id", ondelete="SET NULL")
    )
    # Wer im Webinterface/am Display gehandelt hat (Nachvollziehbarkeit).
    benutzer_id: Mapped[int | None] = mapped_column(
        ForeignKey("benutzer.id", ondelete="SET NULL")
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Mail(Base):
    """Ausgehende Mails als Queue – ohne 4G bleiben sie hier liegen."""

    __tablename__ = "mail"

    id: Mapped[int] = mapped_column(primary_key=True)
    empfaenger: Mapped[str] = mapped_column(String(200))
    betreff: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="offen")
    versuche: Mapped[int] = mapped_column(Integer, default=0)
    letzter_fehler: Mapped[str | None] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    gesendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Wiederholung mit wachsendem Abstand; NULL = sofort versuchen
    naechster_versuch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Einstellung(Base):
    __tablename__ = "einstellung"

    schluessel: Mapped[str] = mapped_column(String(100), primary_key=True)
    wert: Mapped[str] = mapped_column(Text)
