"""Passwörter und Sitzungstoken – nur Standardbibliothek.

scrypt statt bcrypt/argon2: keine nativen Zusatzpakete für ARM nötig und
speicherhart genug für ein Gerät im isolierten LAN.

Sitzung als signiertes Cookie statt Sitzungstabelle: Prüfen kostet keinen
DB-Schreibzugriff pro Klick (Flash schonen). Abgelaufen wird über den
Zeitstempel im Token, ungültig wird es auch, wenn sich das Passwort ändert.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Einstellung

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORT_LAENGE = 8


def _b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def passwort_hash(passwort: str) -> str:
    salz = secrets.token_bytes(16)
    h = hashlib.scrypt(passwort.encode(), salt=salz, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salz)}${_b64(h)}"


def passwort_pruefen(passwort: str, gespeichert: str | None) -> bool:
    if not gespeichert:
        return False
    try:
        verfahren, n, r, p, salz, h = gespeichert.split("$")
        if verfahren != "scrypt":
            return False
        neu = hashlib.scrypt(
            passwort.encode(), salt=_unb64(salz), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(neu, _unb64(h))


def passwort_mangel(passwort: str) -> str | None:
    """Fehlermeldung, wenn das Passwort zu schwach ist, sonst None."""
    if len(passwort) < MIN_PASSWORT_LAENGE:
        return f"Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen haben"
    return None


def passwort_kennung(gespeichert: str | None) -> str:
    """Kurzer Fingerabdruck des Hashes: ändert sich das Passwort, werden alle
    bestehenden Sitzungen ungültig."""
    return hashlib.sha256((gespeichert or "").encode()).hexdigest()[:12]


# ---------- Sitzungstoken ----------

_geheimnis: bytes | None = None


async def geheimnis(session: AsyncSession) -> bytes:
    """Signaturschlüssel, beim ersten Bedarf erzeugt und in `einstellung`
    abgelegt – liegt damit in /data und überlebt Container-Updates."""
    global _geheimnis
    if _geheimnis is None:
        eintrag = await session.get(Einstellung, "web.geheimnis")
        if eintrag is None:
            eintrag = Einstellung(
                schluessel="web.geheimnis", wert=secrets.token_hex(32)
            )
            session.add(eintrag)
            await session.commit()
        _geheimnis = bytes.fromhex(eintrag.wert)
    return _geheimnis


@dataclass
class Token:
    benutzer_id: int
    passwort: str  # passwort_kennung zum Ausstellungszeitpunkt
    zeit: float  # letzte Aktivität (Unix-Zeit)


def token_erstellen(schluessel: bytes, token: Token) -> str:
    nutzlast = _b64(
        json.dumps(
            {"u": token.benutzer_id, "p": token.passwort, "t": int(token.zeit)}
        ).encode()
    )
    signatur = _b64(hmac.new(schluessel, nutzlast.encode(), hashlib.sha256).digest())
    return f"{nutzlast}.{signatur}"


def token_lesen(schluessel: bytes, text: str, max_alter_s: float) -> Token | None:
    try:
        nutzlast, signatur = text.split(".")
        erwartet = hmac.new(schluessel, nutzlast.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(erwartet, _unb64(signatur)):
            return None
        daten = json.loads(_unb64(nutzlast))
        token = Token(int(daten["u"]), str(daten["p"]), float(daten["t"]))
    except (ValueError, KeyError, TypeError):
        return None
    if time.time() - token.zeit > max_alter_s:
        return None
    return token
