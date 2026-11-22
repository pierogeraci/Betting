"""Fase 3 nel portale: contenuti estratti, ricerca, etichettatura, argomenti, emoji, valutazione."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from console.deps import Page, admin_user, csrf_protect, current_user, get_db, open_reviews, redirect, render
from core import queue
from core.analysis import active_classifier, label_counts
from core.media_jobs import request_extraction
from core.models import (
    ElementoGrezzo,
    EmojiSignificato,
    Estrazione,
    Etichetta,
    Media,
    Modello,
    Valutazione,
    utcnow,
)
from core.storage import read_archive

router = APIRouter()
ENTITY_LINE = re.compile(r"^\s*([a-z_]+)\s*[:=]\s*(\S.*?)\s*$")


def extractions(db: Session, element_id: int) -> dict[str, list[Estrazione]]:
    rows = (
        db.execute(
            select(Estrazione)
            .where(Estrazione.elemento_grezzo_id == element_id)
            .order_by(Estrazione.media_id, Estrazione.tempo_inizio_ms.nullsfirst(), Estrazione.id)
        )
        .scalars()
        .all()
    )
    groups: dict[str, list[Estrazione]] = {}
    for row in rows:
        if row.tipo == "analisi" and row.metadati.get("sostituita"):
            continue
        groups.setdefault(row.tipo, []).append(row)
    return groups


@router.get("/fotogramma/{element_id}/{sha}")
def keyframe(element_id: int, sha: str, user=Depends(current_user), db: Session = Depends(get_db)):
    for row in db.execute(
        select(Estrazione).where(Estrazione.elemento_grezzo_id == element_id, Estrazione.tipo == "fotogrammi")
    ).scalars():
        for frame in row.metadati.get("fotogrammi", []):
            if frame.get("sha256") == sha:
                return Response(
                    read_archive(frame["chiave"]),
                    media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"},
                )
    raise HTTPException(404, "Fotogramma non trovato.")


@router.post("/archivio/{element_id}/analizza", dependencies=[Depends(csrf_protect)])
def reanalyse(element_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    element = db.get(ElementoGrezzo, element_id)
    if element is None:
        raise HTTPException(404, "Elemento non trovato.")
    started = 0
    for media in element.media:
        if request_extraction(db, media, translate=True, user_id=user.id):
            started += 1
    if not started:
        queue.enqueue(
            db,
            queue=queue.INTERNAL,
            kind="analizza_testo",
            payload={"elemento_id": element.id},
            user_id=user.id,
        )
    return redirect(
        f"/archivio/{element.id}", "Estrazione dei file in coda." if started else "Analisi del testo in coda."
    )


@router.post("/archivio/{element_id}/etichetta", dependencies=[Depends(csrf_protect)])
def label(
    element_id: int,
    gioco: str = Form(""),
    entita: str = Form(""),
    note: str = Form(""),
    torna: str = Form(""),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    element = db.get(ElementoGrezzo, element_id)
    if element is None:
        raise HTTPException(404, "Elemento non trovato.")
    expected, bad = [], []
    for line in entita.splitlines():
        if not line.strip():
            continue
        m = ENTITY_LINE.match(line)
        if m:
            expected.append({"tipo": m.group(1), "valore": m.group(2)})
        else:
            bad.append(line.strip()[:40])
    if bad:
        return redirect(
            f"/archivio/{element.id}", f"Righe non lette (usa «tipo: valore»): {', '.join(bad[:3])}", "errore"
        )
    row = db.execute(select(Etichetta).where(Etichetta.elemento_grezzo_id == element.id)).scalar_one_or_none()
    if row is None:
        row = Etichetta(elemento_grezzo_id=element.id)
        db.add(row)
    row.pubblicita_gioco = {"si": True, "no": False}.get(gioco)
    row.entita = {"attese": expected, "verificate": True}
    row.note, row.utente_id, row.aggiornato_il = note.strip()[:2000], user.id, utcnow()
    target = torna if torna.startswith("/etichettatura") else f"/archivio/{element.id}"
    return redirect(target, "Etichetta salvata.")


@router.get("/etichettatura")
def labelling(request: Request, fonte: str = "", user=Depends(current_user), db: Session = Depends(get_db)):
    labelled = select(Etichetta.elemento_grezzo_id)
    cond = [ElementoGrezzo.id.not_in(labelled), ElementoGrezzo.tipo.in_(["messaggio", "pagina", "file"])]
    if fonte:
        cond.append(ElementoGrezzo.fonte == fonte)
    queue_rows = (
        db.execute(select(ElementoGrezzo).where(*cond).order_by(func.random()).limit(10)).scalars().all()
    )
    analyses = {}
    for el in queue_rows:
        row = db.execute(
            select(Estrazione)
            .where(Estrazione.elemento_grezzo_id == el.id, Estrazione.tipo == "analisi")
            .order_by(Estrazione.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        analyses[el.id] = row.metadati if row else {}
    return render(
        request,
        "etichettatura.html",
        {
            "sezione": "etichettatura",
            "revisioni": open_reviews(db),
            "righe": queue_rows,
            "analisi": analyses,
            "conteggi": label_counts(db),
            "fonte": fonte,
        },
    )


@router.get("/ricerca-contenuti")
def content_search(
    request: Request,
    q: str = "",
    tipo: str = "",
    pagina: int = 1,
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    results, page = [], Page(1, 0)
    if q.strip():
        tsq = func.websearch_to_tsquery("simple", q.strip())
        extr = select(
            Estrazione.elemento_grezzo_id.label("el"),
            Estrazione.tipo.label("tipo"),
            Estrazione.testo.label("testo"),
            Estrazione.tempo_inizio_ms.label("tempo"),
            Estrazione.media_id.label("media"),
        ).where(
            or_(
                func.to_tsvector("simple", Estrazione.testo).op("@@")(tsq),
                Estrazione.testo.ilike(f"%{q.strip()}%"),
            ),
            Estrazione.tipo != "analisi",
        )
        elems = select(
            ElementoGrezzo.id.label("el"),
            literal("testo").label("tipo"),
            ElementoGrezzo.contenuto.label("testo"),
            literal(None).label("tempo"),
            literal(None).label("media"),
        ).where(
            or_(
                func.to_tsvector("simple", func.coalesce(ElementoGrezzo.contenuto, "")).op("@@")(tsq),
                ElementoGrezzo.contenuto.ilike(f"%{q.strip()}%"),
            )
        )
        union = union_all(extr, elems).subquery()
        query = select(union)
        if tipo in {"ocr", "trascrizione", "qr", "logo", "testo", "traduzione"}:
            query = query.where(union.c.tipo == tipo)
        page = Page(pagina, db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0)
        for row in db.execute(
            query.order_by(union.c.el.desc(), union.c.tempo.nullsfirst()).offset(page.offset).limit(page.size)
        ).all():
            element = db.get(ElementoGrezzo, row.el)
            text = row.testo or ""
            pos = text.lower().find(q.strip().lower().split()[0]) if q.strip() else -1
            snippet = text[max(0, pos - 80) : pos + 160] if pos >= 0 else text[:240]
            results.append(
                {"elemento": element, "tipo": row.tipo, "estratto": snippet, "tempo_ms": row.tempo}
            )
    return render(
        request,
        "ricerca_contenuti.html",
        {
            "sezione": "ricerca",
            "revisioni": open_reviews(db),
            "q": q,
            "tipo": tipo,
            "risultati": results,
            "pag": page,
        },
    )


@router.get("/argomenti")
def topics_page(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.execute(
        select(Modello).where(Modello.nome == "argomenti").order_by(Modello.addestrato_il.desc()).limit(1)
    ).scalar_one_or_none()
    return render(
        request, "argomenti.html", {"sezione": "argomenti", "revisioni": open_reviews(db), "modello": row}
    )


@router.post("/argomenti", dependencies=[Depends(csrf_protect)])
def topics_run(user=Depends(current_user), db: Session = Depends(get_db)):
    queue.enqueue(db, queue=queue.INTERNAL, kind="argomenti", payload={}, user_id=user.id)
    return redirect("/argomenti", "Calcolo degli argomenti in coda.")


@router.get("/emoji")
def emoji_page(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.execute(
            select(EmojiSignificato).order_by(EmojiSignificato.occorrenze.desc(), EmojiSignificato.categoria)
        )
        .scalars()
        .all()
    )
    return render(request, "emoji.html", {"sezione": "emoji", "revisioni": open_reviews(db), "righe": rows})


@router.post("/emoji", dependencies=[Depends(csrf_protect)])
def emoji_save(
    carattere: str = Form(""),
    piattaforma: str = Form(""),
    significato: str = Form(""),
    categoria: str = Form(""),
    user=Depends(admin_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy.dialects.postgresql import insert

    char = carattere.strip()[:16]
    if not char or not significato.strip():
        return redirect("/emoji", "Servono l'emoji e il significato.", "errore")
    db.execute(
        insert(EmojiSignificato)
        .values(
            carattere=char,
            piattaforma=piattaforma.strip()[:20],
            significato=significato.strip()[:200],
            categoria=categoria.strip()[:40],
            occorrenze=0,
        )
        .on_conflict_do_update(
            constraint="emoji_unica",
            set_={"significato": significato.strip()[:200], "categoria": categoria.strip()[:40]},
        )
    )
    return redirect("/emoji", f"Significato di {char} salvato.")


@router.get("/valutazione")
def evaluation_page(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Valutazione).order_by(Valutazione.eseguita_il.desc()).limit(30)).scalars().all()
    _, model = active_classifier(db)
    pending = db.execute(
        select(func.count()).select_from(Media).where(Media.tipo.in_(["immagine", "video", "audio"]))
    ).scalar()
    return render(
        request,
        "valutazione.html",
        {
            "sezione": "valutazione",
            "revisioni": open_reviews(db),
            "righe": rows,
            "modello": model,
            "conteggi": label_counts(db),
            "media": pending,
        },
    )


@router.post("/valutazione/{azione}", dependencies=[Depends(csrf_protect)])
def evaluation_run(azione: str, user=Depends(admin_user), db: Session = Depends(get_db)):
    kind = {"addestra": "addestra_classificatore", "entita": "valuta_entita"}.get(azione)
    if kind is None:
        raise HTTPException(404, "Azione sconosciuta.")
    queue.enqueue(db, queue=queue.INTERNAL, kind=kind, payload={}, user_id=user.id)
    return redirect("/valutazione", "Valutazione in coda: i numeri compaiono qui al termine.")


@router.get("/archivio/{element_id}/testo")
def text_download(
    element_id: int, tipo: str = "trascrizione", user=Depends(current_user), db: Session = Depends(get_db)
):
    rows = (
        db.execute(
            select(Estrazione)
            .where(Estrazione.elemento_grezzo_id == element_id, Estrazione.tipo == tipo)
            .order_by(Estrazione.tempo_inizio_ms.nullsfirst())
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(404, "Nessun testo di questo tipo.")
    lines = []
    for r in rows:
        stamp = (
            f"[{r.tempo_inizio_ms // 60000}:{(r.tempo_inizio_ms // 1000) % 60:02d}] "
            if r.tempo_inizio_ms is not None
            else ""
        )
        lines.append(stamp + r.testo)
    return Response(
        "\n".join(lines),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="elemento-{element_id}-{tipo}.txt"'},
    )
