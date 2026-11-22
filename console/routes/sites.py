"""Elenco dei siti, scheda del sito, prove degli snapshot."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from console.deps import ESITI_ADM, Page, csrf_protect, current_user, get_db, open_reviews, redirect, render
from core import intake
from core.domains import registrable_domain
from core.models import ElementoGrezzo, Entita, Indicatore, Lavoro, MenzioneEntita, Sito, Snapshot, Utente
from core.storage import read_archive

router = APIRouter()
SOURCE_LIMIT = 400_000
SCHEDE = (
    "panoramica",
    "profilazione",
    "trust",
    "puntate",
    "gemelli",
    "legal",
    "grafo",
    "snapshot",
    "traffico",
    "sorgente",
    "origine",
    "lavori",
)


@router.get("/siti")
def sites(
    request: Request,
    q: str = "",
    esito: str = "",
    classe: str = "",
    gruppo: int | None = None,
    pagina: int = 1,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    conditions = []
    if q.strip():
        conditions.append(Sito.dominio.ilike(f"%{q.strip().lower().replace('%', '')}%"))
    if esito in ESITI_ADM:
        conditions.append(Sito.esito_adm == esito)
    if gruppo:
        conditions.append(Sito.gruppo == gruppo)
    if classe in {"basso", "medio", "alto", "nessun_indice"}:
        from core.models import Punteggio

        last_scores = (
            select(
                Punteggio.sito_id,
                Punteggio.classe_rischio,
                func.row_number()
                .over(
                    partition_by=Punteggio.sito_id,
                    order_by=(Punteggio.calcolato_il.desc(), Punteggio.id.desc()),
                )
                .label("n"),
            )
            .where(Punteggio.ambito == "piattaforma")
            .subquery()
        )
        cond = (
            last_scores.c.classe_rischio.is_(None)
            if classe == "nessun_indice"
            else last_scores.c.classe_rischio == classe
        )
        conditions.append(Sito.id.in_(select(last_scores.c.sito_id).where(last_scores.c.n == 1, cond)))
    page = Page(pagina, db.execute(select(func.count()).select_from(Sito).where(*conditions)).scalar() or 0)
    rows = (
        db.execute(
            select(Sito)
            .where(*conditions)
            .order_by(Sito.creato_il.desc())
            .offset(page.offset)
            .limit(page.size)
        )
        .scalars()
        .all()
    )
    latest: dict[int, Snapshot] = {}
    if rows:
        for snap in db.execute(
            select(Snapshot).where(Snapshot.sito_id.in_([s.id for s in rows])).order_by(Snapshot.raccolto_il)
        ).scalars():
            latest[snap.sito_id] = snap
    from console.routes.profile import latest_scores

    scores = {s.id: latest_scores(db, s.id).get("piattaforma") for s in rows}
    name = "parti/siti_tabella.html" if request.headers.get("HX-Request") else "siti.html"
    return render(
        request,
        name,
        {
            "sezione": "siti",
            "revisioni": open_reviews(db),
            "righe": rows,
            "ultimi": latest,
            "punteggi": scores,
            "pag": page,
            "q": q,
            "esito": esito,
            "classe": classe,
            "gruppo": gruppo,
        },
    )


def _site(db: Session, site_id: int) -> Sito:
    site = db.get(Sito, site_id)
    if site is None:
        raise HTTPException(404, "Sito non trovato.")
    return site


def _active_jobs(db: Session, site_id: int) -> list[Lavoro]:
    return (
        db.execute(
            select(Lavoro)
            .where(Lavoro.sito_id == site_id, Lavoro.stato.in_(["in_attesa", "in_corso"]))
            .order_by(Lavoro.id)
        )
        .scalars()
        .all()
    )


def _latest_indicators(db: Session, site_id: int) -> list[Indicatore]:
    seen: dict[str, Indicatore] = {}
    for ind in db.execute(
        select(Indicatore)
        .where(Indicatore.sito_id == site_id)
        .order_by(Indicatore.rilevato_il.desc(), Indicatore.id.desc())
    ).scalars():
        seen.setdefault(ind.codice, ind)
    return sorted(seen.values(), key=lambda i: i.codice)


def parse_har(data: bytes, site_domain: str) -> dict[str, Any]:
    """Riassume il traffico registrato: richieste e domini contattati."""
    try:
        entries = json.loads(data)["log"]["entries"]
    except (ValueError, KeyError, TypeError):
        return {"richieste": [], "domini": [], "totale": 0}
    requests, hosts = [], Counter()
    for entry in entries[:2000]:
        req, resp = entry.get("request", {}), entry.get("response", {})
        url = str(req.get("url", ""))
        host = urlsplit(url).hostname or ""
        hosts[host] += 1
        requests.append(
            {
                "metodo": str(req.get("method", ""))[:10],
                "url": url[:300],
                "host": host,
                "codice": resp.get("status") if isinstance(resp.get("status"), int) else None,
                "tipo": str((resp.get("content") or {}).get("mimeType", "")).split(";")[0][:60],
            }
        )
    domains = [
        {
            "host": host,
            "richieste": count,
            "terza_parte": bool(host) and registrable_domain(host) != site_domain,
        }
        for host, count in hosts.most_common()
    ]
    return {"richieste": requests[:300], "domini": domains, "totale": len(entries)}


@router.get("/siti/{site_id}")
def site_detail(
    request: Request,
    site_id: int,
    scheda: str = "panoramica",
    snapshot: int | None = None,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    site = _site(db, site_id)
    scheda = scheda if scheda in SCHEDE else "panoramica"
    snaps = (
        db.execute(select(Snapshot).where(Snapshot.sito_id == site.id).order_by(Snapshot.raccolto_il.desc()))
        .scalars()
        .all()
    )
    chosen = next((s for s in snaps if s.id == snapshot), snaps[0] if snaps else None)
    context: dict[str, Any] = {
        "sezione": "siti",
        "revisioni": open_reviews(db),
        "sito": site,
        "scheda": scheda,
        "snaps": snaps,
        "snap": chosen,
        "attivi": _active_jobs(db, site.id),
        "indicatori": _latest_indicators(db, site.id),
    }
    from console.routes import profile

    context |= profile.site_context(db, site)
    if scheda == "profilazione":
        context["gruppi"] = profile.grouped_indicators(db, site.id)
    elif scheda in {"legal", "grafo"}:
        from console.routes.fase4 import legal_context

        context |= legal_context(db, site)
    elif scheda == "puntate":
        from core.models import Puntata

        context["lista_puntate"] = (
            db.execute(
                select(Puntata)
                .where(Puntata.sito_id == site.id)
                .order_by(Puntata.momento.desc().nullslast(), Puntata.id.desc())
                .limit(200)
            )
            .scalars()
            .all()
        )
        context["conteggio_puntate"] = dict(
            db.execute(
                select(Puntata.fonte, func.count()).where(Puntata.sito_id == site.id).group_by(Puntata.fonte)
            ).all()
        )
    elif scheda == "trust":
        from core.models import Punteggio

        context["storico"] = (
            db.execute(
                select(Punteggio)
                .where(Punteggio.sito_id == site.id, Punteggio.ambito == "piattaforma")
                .order_by(Punteggio.calcolato_il.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )
    if scheda == "traffico" and chosen and chosen.traffico_chiave:
        context["traffico"] = parse_har(read_archive(chosen.traffico_chiave), site.dominio)
    elif scheda == "sorgente" and chosen and chosen.html_chiave:
        raw = read_archive(chosen.html_chiave)
        context["sorgente"] = raw[:SOURCE_LIMIT].decode("utf-8", "replace")
        context["sorgente_troncata"] = len(raw) > SOURCE_LIMIT
    elif scheda == "origine":
        context["origini"] = (
            db.execute(
                select(ElementoGrezzo)
                .join(MenzioneEntita, MenzioneEntita.elemento_grezzo_id == ElementoGrezzo.id)
                .join(Entita, Entita.id == MenzioneEntita.entita_id)
                .where(Entita.tipo == "dominio", Entita.valore == site.dominio)
                .order_by(ElementoGrezzo.raccolto_il.desc())
                .limit(100)
            )
            .scalars()
            .all()
        )
    elif scheda == "lavori":
        context["lavori"] = (
            db.execute(select(Lavoro).where(Lavoro.sito_id == site.id).order_by(Lavoro.id.desc()).limit(50))
            .scalars()
            .all()
        )
    return render(request, "sito.html", context)


@router.get("/siti/{site_id}/avanzamento")
def site_progress(
    request: Request,
    site_id: int,
    attivo: int = 0,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    site = _site(db, site_id)
    active = _active_jobs(db, site.id)
    response = render(request, "parti/avanzamento.html", {"sito": site, "attivi": active})
    if attivo and not active:
        # I lavori sono finiti: la pagina si ricarica per mostrare il nuovo snapshot.
        response.headers["HX-Refresh"] = "true"
    return response


@router.post("/siti/{site_id}/snapshot", dependencies=[Depends(csrf_protect)])
def site_new_snapshot(site_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    site = _site(db, site_id)
    if _active_jobs(db, site.id):
        return redirect(f"/siti/{site.id}", "C'è già un lavoro in corso per questo sito.", "errore")
    last = db.execute(
        select(Snapshot).where(Snapshot.sito_id == site.id).order_by(Snapshot.raccolto_il.desc()).limit(1)
    ).scalar_one_or_none()
    url = last.url_richiesto if last else f"https://{site.dominio}/"
    intake.request_snapshot(db, site, url, user.id)
    return redirect(f"/siti/{site.id}", "Nuovo snapshot richiesto.")


def _snapshot(db: Session, snapshot_id: int) -> Snapshot:
    snap = db.get(Snapshot, snapshot_id)
    if snap is None:
        raise HTTPException(404, "Snapshot non trovato.")
    return snap


@router.get("/snapshot/{snapshot_id}/schermata")
def snapshot_image(snapshot_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    snap = _snapshot(db, snapshot_id)
    if not snap.schermata_chiave:
        raise HTTPException(404, "Questo snapshot non ha una schermata.")
    return Response(
        read_archive(snap.schermata_chiave),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/snapshot/{snapshot_id}/isolato")
def snapshot_isolated(snapshot_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    """HTML archiviato dentro un riquadro isolato: nessuno script, nessuna risorsa esterna.

    Il contenuto è ostile. La politica `sandbox` gli toglie origine, script e moduli;
    `default-src 'none'` impedisce al browser dell'analista di contattare il sito.
    """
    snap = _snapshot(db, snapshot_id)
    if not snap.html_chiave:
        raise HTTPException(404, "Questo snapshot non ha HTML.")
    return Response(
        read_archive(snap.html_chiave),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@router.get("/snapshot/{snapshot_id}/file/{kind}")
def snapshot_download(
    snapshot_id: int, kind: str, user: Utente = Depends(current_user), db: Session = Depends(get_db)
):
    snap = _snapshot(db, snapshot_id)
    key, name = {
        "html": (snap.html_chiave, f"snapshot-{snap.id}.html.txt"),
        "traffico": (snap.traffico_chiave, f"snapshot-{snap.id}.har.json"),
        "schermata": (snap.schermata_chiave, f"snapshot-{snap.id}.png"),
    }.get(kind, (None, ""))
    if not key:
        raise HTTPException(404, "File non disponibile.")
    return Response(
        read_archive(key),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
