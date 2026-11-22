"""Cruscotto, inserimento, revisione manuale, lavori, archivio grezzo."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from console.deps import Page, admin_user, csrf_protect, current_user, get_db, open_reviews, redirect, render
from console.routes.probes import growth
from core import adm, intake, queue
from core.config import get_settings
from core.domains import InvalidUrl
from core.models import ElementoGrezzo, Lavoro, Media, Revisione, Sito, Utente, utcnow
from core.storage import read_archive

router = APIRouter()
MAX_URLS = 25
ESITI_REVISIONE = {
    "blocco_confermato": "Blocco confermato: la pagina non è leggibile in automatico",
    "da_riprovare": "Da riprovare: richiedi un nuovo snapshot",
    "non_pertinente": "Non pertinente: il sito non riguarda il gioco",
    "verificato_a_mano": "Verificato a mano: vedi le note",
}


def _job_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(Lavoro.stato, func.count()).group_by(Lavoro.stato)).all()
    return {state: count for state, count in rows}


def _dashboard(db: Session) -> dict:
    adm_counts = dict(db.execute(select(Sito.esito_adm, func.count()).group_by(Sito.esito_adm)).all())
    loads = {kind: adm.current_load(db, kind) for kind in adm.ELENCHI}
    return {
        "siti_totali": sum(adm_counts.values()),
        "esiti": adm_counts,
        "lavori": _job_counts(db),
        "revisioni_aperte": open_reviews(db),
        "crescita": growth(db),
        "elenchi": [
            {"tipo": k, "etichetta": adm.ETICHETTE[k], "carico": v, "vecchio": adm.is_stale(v)}
            for k, v in loads.items()
        ],
        "ultimi_siti": db.execute(select(Sito).order_by(Sito.creato_il.desc()).limit(6)).scalars().all(),
        "ultimi_lavori": db.execute(
            select(Lavoro).options(selectinload(Lavoro.sito)).order_by(Lavoro.id.desc()).limit(8)
        )
        .scalars()
        .all(),
    }


@router.get("/")
def dashboard(request: Request, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    return render(
        request,
        "cruscotto.html",
        {"sezione": "cruscotto", "d": _dashboard(db), "revisioni": open_reviews(db)},
    )


@router.get("/cruscotto/riepilogo")
def dashboard_fragment(request: Request, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "parti/cruscotto_riepilogo.html", {"d": _dashboard(db)})


@router.get("/nuovo")
def new_item(request: Request, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    return render(
        request,
        "nuovo.html",
        {
            "sezione": "nuovo",
            "revisioni": open_reviews(db),
            "max_urls": MAX_URLS,
            "max_mb": get_settings().max_upload_mb,
        },
    )


@router.post("/nuovo/url", dependencies=[Depends(csrf_protect)])
def submit_urls(
    request: Request,
    urls: str = Form(""),
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    lines = [line.strip() for line in urls.replace(",", "\n").splitlines() if line.strip()]
    context = {
        "sezione": "nuovo",
        "revisioni": open_reviews(db),
        "max_urls": MAX_URLS,
        "max_mb": get_settings().max_upload_mb,
        "urls": urls,
    }
    if not lines:
        return render(
            request, "nuovo.html", context | {"errore_url": "Inserisci almeno un URL."}, status_code=400
        )
    if len(lines) > MAX_URLS:
        return render(
            request,
            "nuovo.html",
            context | {"errore_url": f"Al massimo {MAX_URLS} URL per volta: ne hai inseriti {len(lines)}."},
            status_code=400,
        )
    accepted, rejected = [], []
    for line in lines:
        try:
            accepted.append(intake.submit_url(db, line, user.id))
        except InvalidUrl as exc:
            rejected.append({"testo": line, "motivo": str(exc)})
    if len(accepted) == 1 and not rejected:
        return redirect(f"/siti/{accepted[0].site.id}", "URL inserito: snapshot e confronto ADM in corso.")
    return render(
        request,
        "nuovo.html",
        context | {"accettati": accepted, "rifiutati": rejected, "urls": ""},
        status_code=200 if accepted else 400,
    )


async def read_upload(upload: UploadFile, max_mb: int) -> bytes:
    limit = max_mb * 1024 * 1024
    chunks, size = [], 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"Il file supera il limite di {max_mb} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/nuovo/file", dependencies=[Depends(csrf_protect)])
async def submit_file(
    request: Request,
    file: UploadFile = File(...),
    nota: str = Form(""),
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = await read_upload(file, get_settings().max_upload_mb)
    try:
        result = intake.submit_file(db, file.filename or "file", data, user.id, nota)
    except ValueError as exc:
        context = {
            "sezione": "nuovo",
            "revisioni": open_reviews(db),
            "max_urls": MAX_URLS,
            "max_mb": get_settings().max_upload_mb,
        }
        return render(request, "nuovo.html", context | {"errore_file": str(exc)}, status_code=400)
    message = (
        "Questo file era già in archivio: nessun duplicato." if result.already_known else "File archiviato."
    )
    return redirect(f"/archivio/{result.element.id}", message)


# --- Revisione manuale -------------------------------------------------------------


@router.get("/revisioni")
def reviews(
    request: Request,
    stato: str = "aperte",
    pagina: int = 1,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Revisione).options(
        selectinload(Revisione.sito), selectinload(Revisione.snapshot), selectinload(Revisione.assegnatario)
    )
    count = select(func.count()).select_from(Revisione)
    if stato == "chiuse":
        cond = Revisione.stato == "chiusa"
    elif stato == "mie":
        cond = (Revisione.assegnata_a == user.id) & (Revisione.stato != "chiusa")
    else:
        stato, cond = "aperte", Revisione.stato != "chiusa"
    page = Page(pagina, db.execute(count.where(cond)).scalar() or 0)
    rows = (
        db.execute(
            query.where(cond).order_by(Revisione.creata_il.desc()).offset(page.offset).limit(page.size)
        )
        .scalars()
        .all()
    )
    return render(
        request,
        "revisioni.html",
        {"sezione": "revisioni", "revisioni": open_reviews(db), "righe": rows, "filtro": stato, "pag": page},
    )


def _review(db: Session, review_id: int) -> Revisione:
    review = db.get(Revisione, review_id)
    if review is None:
        raise HTTPException(404, "Revisione non trovata.")
    return review


@router.get("/revisioni/{review_id}")
def review_detail(
    request: Request, review_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)
):
    review = _review(db, review_id)
    return render(
        request,
        "revisione.html",
        {"sezione": "revisioni", "revisioni": open_reviews(db), "r": review, "esiti": ESITI_REVISIONE},
    )


@router.post("/revisioni/{review_id}/prendi", dependencies=[Depends(csrf_protect)])
def review_take(review_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    review = _review(db, review_id)
    if review.stato == "chiusa":
        return redirect(f"/revisioni/{review_id}", "La revisione è già chiusa.", "errore")
    review.stato, review.assegnata_a = "in_carico", user.id
    return redirect(f"/revisioni/{review_id}", "Revisione presa in carico.")


@router.post("/revisioni/{review_id}/chiudi", dependencies=[Depends(csrf_protect)])
def review_close(
    request: Request,
    review_id: int,
    esito: str = Form(""),
    note: str = Form(""),
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    review = _review(db, review_id)
    if review.stato == "chiusa":
        return redirect(f"/revisioni/{review_id}", "La revisione è già chiusa.", "errore")
    if esito not in ESITI_REVISIONE or not note.strip():
        return render(
            request,
            "revisione.html",
            {
                "sezione": "revisioni",
                "revisioni": open_reviews(db),
                "r": review,
                "esiti": ESITI_REVISIONE,
                "errore": "Scegli un esito e scrivi una nota: serve a chi riesamina il caso.",
                "note": note,
                "esito": esito,
            },
            status_code=400,
        )
    review.stato, review.esito, review.note = "chiusa", esito, note.strip()[:4000]
    review.chiusa_il, review.chiusa_da = utcnow(), user.id
    if review.assegnata_a is None:
        review.assegnata_a = user.id
    message = "Revisione chiusa."
    if esito == "da_riprovare" and review.sito and review.snapshot:
        intake.request_snapshot(db, review.sito, review.snapshot.url_richiesto, user.id)
        message = "Revisione chiusa: richiesto un nuovo snapshot."
    return redirect("/revisioni", message)


# --- Lavori -------------------------------------------------------------------------


def _jobs(db: Session, stato: str, pagina: int):
    cond = Lavoro.stato == stato if stato in {"in_attesa", "in_corso", "completato", "fallito"} else None
    count = select(func.count()).select_from(Lavoro)
    query = select(Lavoro).options(selectinload(Lavoro.sito))
    if cond is not None:
        count, query = count.where(cond), query.where(cond)
    page = Page(pagina, db.execute(count).scalar() or 0, size=30)
    return db.execute(
        query.order_by(Lavoro.id.desc()).offset(page.offset).limit(page.size)
    ).scalars().all(), page


@router.get("/lavori")
def jobs(
    request: Request,
    stato: str = "",
    pagina: int = 1,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows, page = _jobs(db, stato, pagina)
    name = "parti/lavori_tabella.html" if request.headers.get("HX-Request") else "lavori.html"
    return render(
        request,
        name,
        {
            "sezione": "lavori",
            "revisioni": open_reviews(db),
            "righe": rows,
            "pag": page,
            "filtro": stato,
            "conteggi": _job_counts(db),
        },
    )


@router.post("/lavori/{job_id}/riprova", dependencies=[Depends(csrf_protect)])
def job_retry(job_id: int, user: Utente = Depends(admin_user), db: Session = Depends(get_db)):
    job = db.get(Lavoro, job_id)
    if job is None or job.stato != "fallito":
        raise HTTPException(404, "Si possono riprovare solo i lavori falliti.")
    queue.retry(db, job)
    return redirect("/lavori", "Lavoro rimesso in coda.")


# --- Archivio grezzo ----------------------------------------------------------------


@router.get("/archivio")
def archive(
    request: Request,
    fonte: str = "",
    pagina: int = 1,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    count = select(func.count()).select_from(ElementoGrezzo)
    query = select(ElementoGrezzo).options(
        selectinload(ElementoGrezzo.media), selectinload(ElementoGrezzo.autore)
    )
    if fonte:
        cond = ElementoGrezzo.fonte.like(fonte + "%")
        count, query = count.where(cond), query.where(cond)
    page = Page(pagina, db.execute(count).scalar() or 0)
    rows = (
        db.execute(query.order_by(ElementoGrezzo.raccolto_il.desc()).offset(page.offset).limit(page.size))
        .scalars()
        .all()
    )
    return render(
        request,
        "archivio.html",
        {"sezione": "archivio", "revisioni": open_reviews(db), "righe": rows, "pag": page, "fonte": fonte},
    )


@router.get("/archivio/{element_id}")
def archive_detail(
    request: Request, element_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)
):
    element = db.get(ElementoGrezzo, element_id)
    if element is None:
        raise HTTPException(404, "Elemento non trovato.")
    site = None
    if element.tipo == "url" and element.contenuto:
        from core.domains import normalize_url

        try:
            site = db.execute(
                select(Sito).where(Sito.dominio == normalize_url(element.contenuto).registrable)
            ).scalar_one_or_none()
        except InvalidUrl:
            site = None
    return render(
        request,
        "elemento.html",
        {"sezione": "archivio", "revisioni": open_reviews(db), "e": element, "sito": site},
    )


@router.get("/media/{media_id}/scarica")
def media_download(media_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    media = db.get(Media, media_id)
    if media is None:
        raise HTTPException(404, "File non trovato.")
    # Sempre come allegato generico: il browser non deve mai interpretare un file caricato.
    return Response(
        read_archive(media.oggetto_chiave),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(media.nome_file)}"},
    )


@router.get("/ricerca")
def search(q: str = Query(""), user: Utente = Depends(current_user)):
    return redirect(f"/siti?q={quote(q.strip())}")
