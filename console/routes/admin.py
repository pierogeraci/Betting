"""Gestione degli account del portale (solo amministratori)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from console.deps import admin_user, csrf_protect, get_db, open_reviews, redirect, render
from core import security
from core.models import Utente

router = APIRouter()


def _context(db: Session) -> dict:
    return {
        "sezione": "utenti",
        "revisioni": open_reviews(db),
        "utenti": db.execute(select(Utente).order_by(Utente.nome_utente)).scalars().all(),
    }


@router.get("/utenti")
def users(request: Request, user: Utente = Depends(admin_user), db: Session = Depends(get_db)):
    return render(request, "utenti.html", _context(db))


@router.post("/utenti", dependencies=[Depends(csrf_protect)])
def user_create(
    request: Request,
    nome_utente: str = Form(""),
    nome: str = Form(""),
    ruolo: str = Form("analista"),
    password: str = Form(""),
    user: Utente = Depends(admin_user),
    db: Session = Depends(get_db),
):
    try:
        created = security.create_user(db, nome_utente, password, name=nome, role=ruolo)
    except ValueError as exc:
        return render(
            request,
            "utenti.html",
            _context(db)
            | {"errore": str(exc), "form": {"nome_utente": nome_utente, "nome": nome, "ruolo": ruolo}},
            status_code=400,
        )
    return redirect("/utenti", f"Creato l'utente {created.nome_utente}.")


def _target(db: Session, user_id: int) -> Utente:
    target = db.get(Utente, user_id)
    if target is None:
        raise HTTPException(404, "Utente non trovato.")
    return target


@router.post("/utenti/{user_id}/stato", dependencies=[Depends(csrf_protect)])
def user_toggle(user_id: int, user: Utente = Depends(admin_user), db: Session = Depends(get_db)):
    target = _target(db, user_id)
    if target.id == user.id:
        return redirect("/utenti", "Non puoi disattivare il tuo stesso account.", "errore")
    target.attivo = not target.attivo
    if not target.attivo:
        security.close_user_sessions(db, target.id)
    return redirect(
        "/utenti", f"Utente {target.nome_utente} {'riattivato' if target.attivo else 'disattivato'}."
    )


@router.post("/utenti/{user_id}/password", dependencies=[Depends(csrf_protect)])
def user_password(
    user_id: int, password: str = Form(""), user: Utente = Depends(admin_user), db: Session = Depends(get_db)
):
    target = _target(db, user_id)
    problem = security.password_problem(password)
    if problem:
        return redirect("/utenti", problem, "errore")
    target.password_hash = security.hash_password(password)
    target.tentativi_falliti, target.bloccato_fino_a = 0, None
    security.close_user_sessions(db, target.id)
    return redirect("/utenti", f"Password di {target.nome_utente} reimpostata.")
