"""Dipendenze comuni del portale: sessione di database, utente, CSRF, modelli di pagina."""

from __future__ import annotations

import hmac
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core import security
from core.db import session_scope
from core.models import Revisione, SessioneUtente, Utente

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
COOKIE = "sessione"
FLASH = "avviso"

try:
    _ZONE: ZoneInfo | None = ZoneInfo("Europe/Rome")
except Exception:  # noqa: BLE001 - senza dati di fuso orario si resta in UTC
    _ZONE = None

ESITI_ADM = {
    "concessionario": ("Concessionario ADM", "ok"),
    "inibito": ("Inibito da ADM", "danger"),
    "non_in_elenco": ("Non in elenco", "neutral"),
    "non_determinabile": ("Non determinabile", "warn"),
}
STATI = {
    "riuscito": ("Riuscito", "ok"),
    "bloccato": ("Bloccato", "warn"),
    "errore": ("Errore", "danger"),
    "in_attesa": ("In attesa", "neutral"),
    "in_corso": ("In corso", "info"),
    "completato": ("Completato", "ok"),
    "fallito": ("Fallito", "danger"),
    "aperta": ("Aperta", "warn"),
    "in_carico": ("In carico", "info"),
    "chiusa": ("Chiusa", "neutral"),
    "presente": ("Presente", "danger"),
    "assente": ("Assente", "ok"),
    "non_determinabile": ("Non determinabile", "warn"),
    "attivo": ("Attivo", "ok"),
    "sostituito": ("Sostituito", "neutral"),
}
TIPI_LAVORO = {
    "snapshot": "Snapshot della pagina",
    "acquisisci_snapshot": "Acquisizione dello snapshot",
    "confronto_adm": "Confronto con gli elenchi ADM",
    "confronto_adm_tutti": "Riconfronto di tutti i siti",
    "scarica_adm": "Scaricamento elenco ADM",
    "acquisisci_adm": "Caricamento elenco ADM",
}
MOTIVI = {
    "captcha": "Captcha",
    "verifica_antibot": "Verifica anti-bot",
    "accesso_negato": "Accesso negato",
    "limite_richieste": "Troppe richieste",
    "blocco_legale": "Blocco per motivi legali",
    "blocco_geografico": "Blocco geografico",
    "servizio_non_disponibile": "Servizio non disponibile",
}


def _when(value: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    if value is None:
        return "—"
    if _ZONE is not None:
        return value.astimezone(_ZONE).strftime(fmt)
    return value.strftime(fmt) + " UTC"


def _size(value: int | None) -> str:
    size = float(value or 0)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return ""


templates.env.filters["quando"] = _when
templates.env.filters["dimensione"] = _size
templates.env.filters["breve"] = lambda v, n=12: (v or "")[:n]
templates.env.filters["migliaia"] = lambda v: f"{int(v or 0):,}".replace(",", ".")
templates.env.globals.update(ESITI_ADM=ESITI_ADM, STATI=STATI, TIPI_LAVORO=TIPI_LAVORO, MOTIVI=MOTIVI)


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


class LoginRequired(Exception):
    pass


def current_session(request: Request, db: Session = Depends(get_db)) -> SessioneUtente:
    row = security.load_session(db, request.cookies.get(COOKIE))
    if row is None:
        raise LoginRequired
    request.state.sessione = row
    return row


def current_user(row: SessioneUtente = Depends(current_session)) -> Utente:
    return row.utente


def admin_user(user: Utente = Depends(current_user)) -> Utente:
    if user.ruolo != "amministratore":
        raise HTTPException(403, "Operazione riservata agli amministratori.")
    return user


async def csrf_protect(request: Request, row: SessioneUtente = Depends(current_session)) -> None:
    """Ogni richiesta che modifica dati deve portare il gettone della sessione."""
    token = request.headers.get("X-CSRF-Token")
    if token is None:
        form = await request.form()
        token = str(form.get("csrf", ""))
    if not hmac.compare_digest(token, row.csrf):
        raise HTTPException(403, "Richiesta non valida: ricarica la pagina e riprova.")


def flash(response: Response, message: str, kind: str = "ok") -> Response:
    response.set_cookie(FLASH, quote(f"{kind}|{message}"[:400]), max_age=30, httponly=True, samesite="lax")
    return response


def redirect(url: str, message: str | None = None, kind: str = "ok") -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    if message:
        flash(response, message, kind)
    return response


def render(
    request: Request, name: str, context: dict[str, Any] | None = None, status_code: int = 200
) -> Response:
    ctx: dict[str, Any] = dict(context or {})
    row: SessioneUtente | None = getattr(request.state, "sessione", None)
    ctx.setdefault("utente", row.utente if row else None)
    ctx.setdefault("csrf", row.csrf if row else "")
    raw = request.cookies.get(FLASH)
    if raw and "|" in unquote(raw):
        kind, message = unquote(raw).split("|", 1)
        ctx["avviso"] = {"tipo": kind if kind in {"ok", "errore"} else "ok", "testo": message}
    response = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    if raw:
        response.delete_cookie(FLASH)
    return response


def open_reviews(db: Session) -> int:
    return (
        db.execute(select(func.count()).select_from(Revisione).where(Revisione.stato != "chiusa")).scalar()
        or 0
    )


class Page:
    """Paginazione semplice per gli elenchi."""

    def __init__(self, page: int, total: int, size: int = 25) -> None:
        self.size = size
        self.total = total
        self.pages = max(1, (total + size - 1) // size)
        self.number = min(max(1, page), self.pages)
        self.offset = (self.number - 1) * size
        self.first = self.offset + 1 if total else 0
        self.last = min(total, self.offset + size)
