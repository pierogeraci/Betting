"""Password e sessioni del portale, con la sola libreria standard."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import SessioneUtente, Utente, utcnow

_N, _R, _P = 2**15, 8, 1
MAX_FAILED = 5
LOCK_MINUTES = 15
MIN_PASSWORD = 12


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=2**27, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=2**27,
            dklen=32,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"La password deve avere almeno {MIN_PASSWORD} caratteri."
    return None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(session: Session, username: str, password: str) -> Utente | None:
    """Verifica le credenziali. Dopo troppi errori l'account resta bloccato per alcuni minuti."""
    user = session.query(Utente).filter(Utente.nome_utente == username.strip().lower()).one_or_none()
    if user is None or not user.attivo:
        # Stesso costo di calcolo anche quando l'utente non esiste.
        verify_password(password, "scrypt$32768$8$1$00$00")
        return None
    now = utcnow()
    if user.bloccato_fino_a and user.bloccato_fino_a > now:
        return None
    if not verify_password(password, user.password_hash):
        user.tentativi_falliti += 1
        if user.tentativi_falliti >= MAX_FAILED:
            user.bloccato_fino_a = now + timedelta(minutes=LOCK_MINUTES)
            user.tentativi_falliti = 0
        session.flush()
        return None
    user.tentativi_falliti = 0
    user.bloccato_fino_a = None
    session.flush()
    return user


def open_session(session: Session, user: Utente) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        SessioneUtente(
            token_hash=_token_hash(token),
            utente_id=user.id,
            csrf=secrets.token_urlsafe(24),
            scade_il=utcnow() + timedelta(hours=get_settings().session_hours),
        )
    )
    session.flush()
    return token


def load_session(session: Session, token: str | None) -> SessioneUtente | None:
    if not token:
        return None
    row = session.get(SessioneUtente, _token_hash(token))
    if row is None:
        return None
    if row.scade_il <= utcnow() or not row.utente.attivo:
        session.delete(row)
        session.flush()
        return None
    return row


def close_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(SessioneUtente).where(SessioneUtente.token_hash == _token_hash(token)))


def close_user_sessions(session: Session, user_id: int) -> None:
    session.execute(delete(SessioneUtente).where(SessioneUtente.utente_id == user_id))


def create_user(
    session: Session, username: str, password: str, name: str = "", role: str = "analista"
) -> Utente:
    username = username.strip().lower()
    if (
        not username
        or len(username) > 64
        or not username.replace(".", "").replace("_", "").replace("-", "").isalnum()
    ):
        raise ValueError("Nome utente non valido: usa lettere, cifre, punto, trattino.")
    if role not in {"analista", "amministratore"}:
        raise ValueError("Ruolo non valido.")
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    if session.query(Utente).filter(Utente.nome_utente == username).count():
        raise ValueError("Esiste già un utente con questo nome.")
    user = Utente(nome_utente=username, nome=name.strip(), password_hash=hash_password(password), ruolo=role)
    session.add(user)
    session.flush()
    return user
