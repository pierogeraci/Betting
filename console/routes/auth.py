from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from console.deps import COOKIE, csrf_protect, current_user, get_db, redirect, render
from core import security
from core.config import get_settings
from core.models import Utente

router = APIRouter()


@router.get("/accesso")
def login_page(request: Request, db: Session = Depends(get_db)):
    if security.load_session(db, request.cookies.get(COOKIE)):
        return redirect("/")
    return render(request, "accesso.html", {})


@router.post("/accesso")
def login(
    request: Request, nome_utente: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)
):
    user = security.authenticate(db, nome_utente, password)
    if user is None:
        db.commit()  # conserva il conteggio dei tentativi falliti
        return render(
            request,
            "accesso.html",
            {
                "errore": "Nome utente o password non corretti. Dopo cinque errori l'accesso resta bloccato per 15 minuti.",
                "nome_utente": nome_utente,
            },
            status_code=401,
        )
    token = security.open_session(db, user)
    response = redirect("/")
    settings = get_settings()
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
    )
    return response


@router.post("/uscita", dependencies=[Depends(csrf_protect)])
def logout(request: Request, db: Session = Depends(get_db)):
    security.close_session(db, request.cookies.get(COOKIE))
    response = redirect("/accesso")
    response.delete_cookie(COOKIE)
    return response


@router.get("/profilo")
def profile(request: Request, user: Utente = Depends(current_user)):
    return render(request, "profilo.html", {"sezione": "profilo"})


@router.post("/profilo/password", dependencies=[Depends(csrf_protect)])
def change_password(
    request: Request,
    attuale: str = Form(""),
    nuova: str = Form(""),
    conferma: str = Form(""),
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    problem = None
    if not security.verify_password(attuale, user.password_hash):
        problem = "La password attuale non è corretta."
    elif nuova != conferma:
        problem = "Le due nuove password non coincidono."
    else:
        problem = security.password_problem(nuova)
    if problem:
        return render(request, "profilo.html", {"sezione": "profilo", "errore": problem}, status_code=400)
    user.password_hash = security.hash_password(nuova)
    return redirect("/profilo", "Password aggiornata.")
