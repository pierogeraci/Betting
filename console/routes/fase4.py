"""Fase 4 nel portale: app Android, legal entity e grafo, registri, anomalie sintetiche, eventi sportivi."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from console.deps import admin_user, csrf_protect, current_user, get_db, open_reviews, redirect, render
from console.routes.pages import read_upload
from core import legal
from core.apk import request_apk_analysis
from core.models import (
    ElementoGrezzo,
    Estrazione,
    EventoSportivo,
    LegalEntity,
    Media,
    Modello,
    QuotaEvento,
    RegistroVoce,
    Sito,
    utcnow,
)
from core.storage import archive_bytes
from scoring import anomalies, events

router = APIRouter()


def _site(db: Session, site_id: int) -> Sito:
    site = db.get(Sito, site_id)
    if site is None:
        raise HTTPException(404, "Sito non trovato.")
    return site


def legal_context(db: Session, site: Sito) -> dict:
    return {
        "candidati": legal.candidates(db, site),
        "grafo": legal.graph(db, site),
        "legal_confermate": db.execute(
            select(LegalEntity).where(LegalEntity.sito_id == site.id).order_by(LegalEntity.creato_il.desc())
        )
        .scalars()
        .all(),
        "registri": dict(
            db.execute(select(RegistroVoce.registro, func.count()).group_by(RegistroVoce.registro)).all()
        ),
    }


@router.post("/siti/{site_id}/legal", dependencies=[Depends(csrf_protect)])
def legal_decide(
    site_id: int,
    nome: str = Form(""),
    decisione: str = Form(""),
    note: str = Form(""),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    site = _site(db, site_id)
    candidate = next((c for c in legal.candidates(db, site) if c["nome"] == nome), None)
    if candidate is None and decisione == "aggiungi" and nome.strip():
        candidate = {
            "nome": nome.strip(),
            "punteggio": 0,
            "evidenze": [{"peso": 0, "evidenza": f"Indicata a mano da {user.nome_utente}"}],
        }
    if candidate is None or decisione not in {"conferma", "respingi", "aggiungi"}:
        return redirect(f"/siti/{site.id}?scheda=legal", "Candidato non trovato.", "errore")
    legal.confirm(db, site, candidate, user.id, accept=decisione != "respingi", note=note)
    return redirect(
        f"/siti/{site.id}?scheda=legal",
        f"{candidate['nome']}: {'respinta' if decisione == 'respingi' else 'confermata'}.",
    )


@router.get("/registri")
def registries(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    counts = db.execute(
        select(RegistroVoce.registro, RegistroVoce.fonte, func.count()).group_by(
            RegistroVoce.registro, RegistroVoce.fonte
        )
    ).all()
    return render(
        request, "registri.html", {"sezione": "registri", "revisioni": open_reviews(db), "conteggi": counts}
    )


@router.post("/registri", dependencies=[Depends(csrf_protect)])
async def registry_upload(
    registro: str = Form(""),
    fonte: str = Form(""),
    file: UploadFile = File(...),
    user=Depends(admin_user),
    db: Session = Depends(get_db),
):
    data = await read_upload(file, 50)
    if not fonte.strip():
        return redirect(
            "/registri",
            "Indica la fonte del registro (per esempio: Curaçao Gaming Authority, novembre 2026).",
            "errore",
        )
    try:
        count, errors = legal.load_registry(db, registro, data, fonte.strip(), user.id)
    except ValueError as exc:
        return redirect("/registri", str(exc), "errore")
    return redirect(
        "/registri",
        f"Caricate {count} voci." + (f" {len(errors)} righe scartate." if errors else ""),
        "ok" if count else "errore",
    )


# --- App Android ----------------------------------------------------------------------


@router.get("/app")
def apps(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.execute(select(Media).where(Media.tipo == "apk").order_by(Media.creato_il.desc()).limit(200))
        .scalars()
        .all()
    )
    analyses = {}
    for media in rows:
        found = (
            db.execute(
                select(Estrazione)
                .where(
                    Estrazione.media_id == media.id,
                    Estrazione.tipo.in_(["apk", "apk_traffico", "apk_errore"]),
                )
                .order_by(Estrazione.id)
            )
            .scalars()
            .all()
        )
        analyses[media.id] = {e.tipo: e for e in found}
    return render(
        request,
        "app.html",
        {"sezione": "app", "revisioni": open_reviews(db), "righe": rows, "analisi": analyses},
    )


@router.post("/app/{media_id}/{tipo}", dependencies=[Depends(csrf_protect)])
def app_analyse(media_id: int, tipo: str, user=Depends(admin_user), db: Session = Depends(get_db)):
    media = db.get(Media, media_id)
    if media is None or media.tipo != "apk":
        raise HTTPException(404, "APK non trovato.")
    job = request_apk_analysis(db, media, user.id, dynamic=tipo == "dinamica")
    if job is None:
        msg = "Serve prima l'analisi statica." if tipo == "dinamica" else "Analisi già in coda."
        return redirect("/app", msg, "errore")
    return redirect("/app", "Analisi in coda nel contenitore isolato delle app.")


# --- Anomalie su dati sintetici ---------------------------------------------------------


@router.get("/anomalie")
def anomalies_page(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.execute(
        select(Modello).where(Modello.nome == "anomalie").order_by(Modello.addestrato_il.desc()).limit(1)
    ).scalar_one_or_none()
    return render(
        request,
        "anomalie.html",
        {
            "sezione": "anomalie",
            "revisioni": open_reviews(db),
            "modello": row,
            "regole": anomalies.RULES,
            "schemi": anomalies.PATTERNS,
        },
    )


@router.post("/anomalie", dependencies=[Depends(csrf_protect)])
def anomalies_run(
    conti: int = Form(300),
    quota: float = Form(0.06),
    seme: int = Form(7),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    conti, quota = max(50, min(conti, 5000)), max(0.01, min(quota, 0.3))
    result = anomalies.run(conti, quota, seme)
    db.add(
        Modello(nome="anomalie", versione=f"sintetico-{conti}-{seme}", metriche=result, addestrato_da=user.id)
    )
    return redirect("/anomalie", f"Analisi su {conti} conti sintetici completata.")


# --- Eventi sportivi ------------------------------------------------------------------------


@router.get("/eventi")
def events_page(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.execute(select(EventoSportivo).order_by(EventoSportivo.inizio.desc().nullslast()).limit(200))
        .scalars()
        .all()
    )
    return render(request, "eventi.html", {"sezione": "eventi", "revisioni": open_reviews(db), "righe": rows})


@router.post("/eventi", dependencies=[Depends(csrf_protect)])
async def events_upload(
    file: UploadFile = File(...),
    fonte: str = Form(""),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    data = await read_upload(file, 50)
    try:
        rows, errors = events.parse_csv(data)
    except ValueError as exc:
        return redirect("/eventi", str(exc), "errore")
    if not rows:
        return redirect("/eventi", "Nessuna riga valida.", "errore")
    digest, key = archive_bytes(data, "text/csv")
    element = ElementoGrezzo(
        fonte="manuale:quote",
        tipo="quote",
        riferimento=(fonte or file.filename or "quote.csv")[:300],
        oggetto_chiave=key,
        sha256=digest,
        inserito_da=user.id,
        metadati={"righe": len(rows)},
    )
    exists = db.execute(
        select(ElementoGrezzo.id).where(
            ElementoGrezzo.fonte == "manuale:quote", ElementoGrezzo.sha256 == digest
        )
    ).first()
    if exists:
        return redirect("/eventi", "Questo file è già stato caricato.", "errore")
    db.add(element)
    db.flush()
    grouped: dict[tuple, list] = {}
    for r in rows:
        grouped.setdefault((r["evento"], r["inizio"]), []).append(r)
    for (name, start), quotes in grouped.items():
        event = db.execute(
            select(EventoSportivo).where(
                EventoSportivo.nome == name,
                EventoSportivo.inizio == start if start else EventoSportivo.inizio.is_(None),
            )
        ).scalar_one_or_none()
        if event is None:
            event = EventoSportivo(
                nome=name,
                inizio=start,
                sport=quotes[0]["sport"],
                competizione=quotes[0]["competizione"],
                elemento_grezzo_id=element.id,
            )
            db.add(event)
            db.flush()
        for q in quotes:
            db.add(
                QuotaEvento(
                    evento_id=event.id,
                    bookmaker=q["bookmaker"],
                    momento=q["momento"] or utcnow(),
                    esito=q["esito"],
                    quota=q["quota"],
                    volume=q["volume"],
                )
            )
        db.flush()
        all_quotes = [
            {
                "bookmaker": x.bookmaker,
                "momento": x.momento,
                "esito": x.esito,
                "quota": float(x.quota),
                "volume": float(x.volume) if x.volume is not None else None,
            }
            for x in db.execute(select(QuotaEvento).where(QuotaEvento.evento_id == event.id)).scalars()
        ]
        result = events.rate(all_quotes, event.inizio)
        event.rating, event.dettaglio = result["rating"], result
    return redirect(
        "/eventi", f"Caricati {len(grouped)} eventi." + (f" {len(errors)} righe scartate." if errors else "")
    )


@router.get("/eventi/{event_id}")
def event_detail(request: Request, event_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    event = db.get(EventoSportivo, event_id)
    if event is None:
        raise HTTPException(404, "Evento non trovato.")
    quotes = (
        db.execute(select(QuotaEvento).where(QuotaEvento.evento_id == event.id).order_by(QuotaEvento.momento))
        .scalars()
        .all()
    )
    return render(
        request,
        "evento.html",
        {
            "sezione": "eventi",
            "revisioni": open_reviews(db),
            "ev": event,
            "grafici": odds_charts(quotes, event.inizio),
        },
    )


def odds_charts(quotes: list[QuotaEvento], start) -> list[dict]:
    """Una serie per bookmaker e per esito, già scalata in coordinate 0-100 per l'SVG."""
    if not quotes:
        return []
    t0, t1 = min(q.momento for q in quotes), max(q.momento for q in quotes)
    span = (t1 - t0).total_seconds() or 1
    charts = []
    for outcome in sorted({q.esito for q in quotes}):
        rows = [q for q in quotes if q.esito == outcome]
        lo, hi = min(float(q.quota) for q in rows), max(float(q.quota) for q in rows)
        rng = (hi - lo) or 1
        series = []
        for book in sorted({q.bookmaker for q in rows}):
            pts = [
                ((q.momento - t0).total_seconds() / span * 100, 90 - (float(q.quota) - lo) / rng * 80)
                for q in rows
                if q.bookmaker == book
            ]
            series.append(
                {
                    "bookmaker": book,
                    "punti": " ".join(f"{x:.2f},{y:.2f}" for x, y in pts),
                    "ultima": float([q for q in rows if q.bookmaker == book][-1].quota),
                }
            )
        mark = None
        if start and t0 <= start - timedelta(hours=events.LATE_HOURS) <= t1:
            mark = ((start - timedelta(hours=events.LATE_HOURS)) - t0).total_seconds() / span * 100
        charts.append(
            {
                "esito": outcome,
                "serie": series,
                "min": lo,
                "max": hi,
                "inizio": t0,
                "fine": t1,
                "finale": mark,
            }
        )
    return charts
