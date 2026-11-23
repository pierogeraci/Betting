"""Elenchi ADM: versioni caricate, nuovo caricamento, ricerca di un dominio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from console.deps import admin_user, csrf_protect, current_user, get_db, open_reviews, redirect, render
from console.routes.pages import read_upload
from core import adm, queue
from core.domains import find_domain
from core.models import AdmCaricamento, Lavoro, Utente
from core.sources import adm_sources

router = APIRouter()


def _context(db: Session) -> dict:
    return {
        "sezione": "adm",
        "revisioni": open_reviews(db),
        "elenchi": [
            {
                "tipo": k,
                "etichetta": adm.ETICHETTE[k],
                "carico": adm.current_load(db, k),
                "vecchio": adm.is_stale(adm.current_load(db, k)),
                "fonte": adm_sources().get(k),
            }
            for k in adm.ELENCHI
        ],
        "storico": db.execute(select(AdmCaricamento).order_by(AdmCaricamento.caricato_il.desc()).limit(30))
        .scalars()
        .all(),
        "etichette": adm.ETICHETTE,
    }


@router.get("/adm")
def adm_page(request: Request, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "adm.html", _context(db))


@router.get("/adm/cerca")
def adm_search(
    request: Request, dominio: str = "", user: Utente = Depends(current_user), db: Session = Depends(get_db)
):
    host = find_domain(dominio) if dominio.strip() else None
    results = adm.compare_hosts(db, [host]) if host else None
    return render(
        request,
        "parti/adm_ricerca.html",
        {
            "dominio": dominio,
            "host": host,
            "risultati": results,
            "etichette": adm.ETICHETTE,
            "sintesi": adm.summarize(results) if results else None,
        },
    )


@router.post("/adm/carica", dependencies=[Depends(csrf_protect)])
async def adm_upload(
    request: Request,
    elenco: str = Form(""),
    file: UploadFile = File(...),
    user: Utente = Depends(admin_user),
    db: Session = Depends(get_db),
):
    data = await read_upload(file, 60)
    try:
        if elenco not in adm.ELENCHI:
            raise adm.UnsupportedList("Scegli quale elenco stai caricando.")
        load, created = adm.load_list(db, elenco, data, filename=file.filename or "", user_id=user.id)
    except adm.UnsupportedList as exc:
        return render(request, "adm.html", _context(db) | {"errore": str(exc)}, status_code=400)
    if not created:
        return redirect(
            "/adm", "Il file è identico alla versione attiva: aggiornata solo la data di verifica."
        )
    return redirect(
        "/adm",
        f"{adm.ETICHETTE[elenco]}: caricata la versione {load.versione} con {load.righe_valide} domini. Riconfronto dei siti in corso.",
    )


@router.post("/adm/scarica", dependencies=[Depends(csrf_protect)])
def adm_download(elenco: str = Form(""), user: Utente = Depends(admin_user), db: Session = Depends(get_db)):
    url = adm_sources().get(elenco)
    if not url:
        return redirect(
            "/adm", "Per questo elenco non è configurato alcun indirizzo: caricalo da file.", "errore"
        )
    pending = db.execute(
        select(Lavoro.id).where(
            Lavoro.tipo == "scarica_adm",
            Lavoro.stato.in_(["in_attesa", "in_corso"]),
            Lavoro.carico["elenco"].astext == elenco,
        )
    ).first()
    if pending:
        return redirect("/adm", "Lo scaricamento è già in coda.", "errore")
    queue.enqueue(
        db,
        queue=queue.COLLECT,
        kind="scarica_adm",
        payload={"elenco": elenco, "url": url},
        next_kind="acquisisci_adm",
        user_id=user.id,
        max_attempts=2,
    )
    return redirect("/adm", "Scaricamento messo in coda: lo esegue il contenitore di raccolta.")
