"""E-Mail: Einreihen in die Queue und Versand per SMTP.

Versand über smtplib (Standardbibliothek) in einem Thread – keine Zusatzpakete,
und ein hängender Mailserver blockiert die Ereignisschleife nicht.
Ohne Konfiguration oder ohne Netz bleiben Mails einfach in der Queue
(Lastenheft: kein 4G → Automat arbeitet weiter).
"""

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import einstellungen
from app.db.models import Mail

SMTP_TIMEOUT_S = 20


@dataclass(frozen=True)
class SmtpKonfig:
    host: str
    port: int
    sicherheit: str  # starttls | ssl | keine
    benutzer: str
    passwort: str
    absender: str


async def konfig(session: AsyncSession) -> SmtpKonfig | None:
    """None, solange Server oder Absender fehlen – dann wird nicht versucht."""
    werte = await einstellungen.alle(session)
    if not werte["smtp.host"] or not werte["smtp.absender"]:
        return None
    return SmtpKonfig(
        host=werte["smtp.host"],
        port=int(werte["smtp.port"] or 587),
        sicherheit=werte["smtp.sicherheit"] or "starttls",
        benutzer=werte["smtp.benutzer"],
        passwort=werte["smtp.passwort"],
        absender=werte["smtp.absender"],
    )


def einreihen(session: AsyncSession, empfaenger: str, betreff: str, text: str) -> None:
    """Mail in die Queue; Commit macht der Aufrufer (gleiche Transaktion wie der
    Anlass – keine Mail für einen Vorgang, der zurückgerollt wurde)."""
    session.add(
        Mail(
            empfaenger=empfaenger,
            betreff=betreff,
            text=text,
            status="offen",
            versuche=0,
        )
    )


def _senden_sync(k: SmtpKonfig, empfaenger: str, betreff: str, text: str) -> None:
    # EmailMessage kodiert Umlaute und verhindert Header-Injection über Betreff/
    # Empfänger (Zeilenumbrüche werden abgewiesen).
    nachricht = EmailMessage()
    nachricht["From"] = k.absender
    nachricht["To"] = empfaenger
    nachricht["Subject"] = betreff
    nachricht["Date"] = formatdate(localtime=True)
    nachricht["Message-ID"] = make_msgid(domain=k.absender.rsplit("@", 1)[-1])
    nachricht.set_content(text)

    kontext = ssl.create_default_context()
    if k.sicherheit == "ssl":
        server = smtplib.SMTP_SSL(
            k.host, k.port, timeout=SMTP_TIMEOUT_S, context=kontext
        )
    else:
        server = smtplib.SMTP(k.host, k.port, timeout=SMTP_TIMEOUT_S)
    with server:
        if k.sicherheit == "starttls":
            server.starttls(context=kontext)
        if k.benutzer:
            server.login(k.benutzer, k.passwort)
        server.send_message(nachricht)


async def senden(k: SmtpKonfig, empfaenger: str, betreff: str, text: str) -> None:
    """Wirft bei jedem Fehler (Netz, Anmeldung, Empfänger abgelehnt)."""
    await asyncio.to_thread(_senden_sync, k, empfaenger, betreff, text)
