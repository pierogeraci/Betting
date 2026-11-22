"""Fase 1 nel portale: profilazione, Trust Index, puntate, gemelli, giudizio, validazione, report."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from console.deps import csrf_protect, current_user, get_db, open_reviews, redirect, render, templates
from console.routes.pages import read_upload
from core import profiling, queue
from core.bets import parse_upload
from core.models import (
    ElementoGrezzo,
    LegalEntity,
    Puntata,
    Punteggio,
    Revisione,
    Sito,
    Snapshot,
    Utente,
    utcnow,
)
from core.storage import archive_bytes
from scoring.config import load_rules

router = APIRouter()

AREE = {
    "elenchi_adm": "Elenchi ADM",
    "titolo_operare": "Titolo a operare",
    "dati_aziendali": "Dati aziendali",
    "pagamenti": "Pagamenti",
    "identificazione": "Identificazione",
    "offerta": "Offerta",
    "infrastruttura": "Infrastruttura",
}
NOMI_INDICATORI = {
    "dominio_concessionario_adm": "Dominio nell'elenco dei concessionari",
    "dominio_inibito_adm": "Dominio nell'elenco dei siti inibiti",
    "logo_adm_esposto": "Logo ADM esposto",
    "numero_concessione_dichiarato": "Numero di concessione dichiarato",
    "licenza_estera_dichiarata": "Licenza estera dichiarata",
    "ragione_sociale_dichiarata": "Ragione sociale",
    "partita_iva_dichiarata": "Partita IVA o numero di registrazione",
    "sede_dichiarata": "Sede",
    "pagamento_conto_ue": "Pagamento da conto corrente UE",
    "pagamento_terze_parti": "Pagamento tramite fornitori terzi",
    "pagamento_criptovalute": "Pagamento e puntata in criptovalute",
    "pagamento_offshore": "Pagamento su conto offshore",
    "assenza_registrazione": "Assenza di registrazione",
    "assenza_documento": "Nessun documento richiesto",
    "piu_account_per_conto": "Più account collegati a un unico conto",
    "tipi_gioco": "Tipi di gioco offerti",
    "quote_visibili": "Quote visibili senza accesso",
    "chat_dal_vivo": "Chat dal vivo esterna",
    "immagini_esterne": "Immagini servite da servizi esterni",
    "link_pagamento_rapido": "Link di pagamento rapido",
    "lingua_italiana": "Pagine in italiano",
    "identificativi_tracciamento": "Identificativi di tracciamento",
    "impronta_html": "Impronta della struttura HTML",
    "domini_terze_parti": "Domini di terze parti contattati",
    "icona_sito": "Icona del sito",
    "dati_rete": "DNS, registrazione, certificato",
}
CLASSI_ANALISTA = {
    "basso": "Rischio basso",
    "medio": "Rischio medio",
    "alto": "Rischio alto",
    "legale": "Sito legale (concessionario)",
}
OBIETTIVO_VALIDAZIONE = 50

templates.env.globals.update(AREE=AREE, NOMI_INDICATORI=NOMI_INDICATORI, CLASSI_ANALISTA=CLASSI_ANALISTA)


def _site(db: Session, site_id: int) -> Sito:
    site = db.get(Sito, site_id)
    if site is None:
        raise HTTPException(404, "Sito non trovato.")
    return site


def latest_scores(db: Session, site_id: int) -> dict[str, Punteggio]:
    out: dict[str, Punteggio] = {}
    for row in db.execute(
        select(Punteggio)
        .where(Punteggio.sito_id == site_id)
        .order_by(Punteggio.calcolato_il.desc(), Punteggio.id.desc())
    ).scalars():
        out.setdefault(row.ambito, row)
    return out


def latest_judgement(db: Session, site_id: int) -> Revisione | None:
    return db.execute(
        select(Revisione)
        .where(Revisione.sito_id == site_id, Revisione.tipo == "giudizio")
        .order_by(Revisione.creata_il.desc())
        .limit(1)
    ).scalar_one_or_none()


def grouped_indicators(db: Session, site_id: int) -> dict[str, list]:
    groups: dict[str, list] = {}
    for _code, ind in sorted(profiling.latest_indicators(db, site_id).items()):
        groups.setdefault(AREE.get(ind.collettore, ind.collettore), []).append(ind)
    order = list(AREE.values())
    return dict(sorted(groups.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))


def site_context(db: Session, site: Sito) -> dict[str, Any]:
    scores = latest_scores(db, site.id)
    return {
        "punteggi": scores,
        "punteggio": scores.get("piattaforma"),
        "giudizio": latest_judgement(db, site.id),
        "regole": load_rules(),
        "gemelli": profiling.twins_of(db, site.id),
    }


@router.get("/siti/{site_id}/profilo")
def profile_tab(
    request: Request, site_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)
):
    from console.routes.sites import site_detail

    return site_detail(request, site_id, "profilazione", None, user, db)


@router.post("/siti/{site_id}/profila", dependencies=[Depends(csrf_protect)])
def profile_again(site_id: int, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    site = _site(db, site_id)
    job = profiling.request_profile(db, site, user.id)
    return redirect(
        f"/siti/{site.id}?scheda=profilazione",
        "Profilazione rimessa in coda." if job else "Profilazione già in coda.",
    )


@router.post("/siti/{site_id}/puntate", dependencies=[Depends(csrf_protect)])
async def bets_upload(
    request: Request,
    site_id: int,
    file: UploadFile = File(...),
    sostituisci: str = Form(""),
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    site = _site(db, site_id)
    data = await read_upload(file, 20)
    try:
        rows, errors = parse_upload(data)
    except ValueError as exc:
        return redirect(f"/siti/{site.id}?scheda=puntate", str(exc), "errore")
    if not rows:
        return redirect(
            f"/siti/{site.id}?scheda=puntate",
            "Nessuna riga valida nel file. " + "; ".join(errors[:3]),
            "errore",
        )
    digest, key = archive_bytes(data, "text/csv")
    element = db.execute(
        select(ElementoGrezzo).where(
            ElementoGrezzo.fonte == "manuale:puntate", ElementoGrezzo.sha256 == digest
        )
    ).scalar_one_or_none()
    if element is None:
        element = ElementoGrezzo(
            fonte="manuale:puntate",
            tipo="puntate",
            riferimento=f"{site.dominio}: {file.filename or 'puntate.csv'}",
            oggetto_chiave=key,
            sha256=digest,
            inserito_da=user.id,
            metadati={"righe": len(rows), "sito_id": site.id},
        )
        db.add(element)
        db.flush()
    if sostituisci:
        profiling.clear_bets(db, site.id, "caricata")
    for row in rows:
        db.add(
            Puntata(
                sito_id=site.id,
                tipo_gioco=row.game,
                importo_puntato=row.stake,
                importo_vinto=row.won,
                valuta=row.currency,
                momento=row.at,
                fonte="caricata",
                elemento_grezzo_id=element.id,
            )
        )
    queue.enqueue(
        db,
        queue=queue.INTERNAL,
        kind="punteggio",
        payload={"sito_id": site.id},
        site_id=site.id,
        user_id=user.id,
    )
    message = f"Caricate {len(rows)} puntate: punteggio in ricalcolo."
    if errors:
        message += f" {len(errors)} righe scartate (la prima: {errors[0]})."
    return redirect(f"/siti/{site.id}?scheda=trust", message)


@router.post("/siti/{site_id}/giudizio", dependencies=[Depends(csrf_protect)])
def judgement(
    site_id: int,
    classe: str = Form(""),
    note: str = Form(""),
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    site = _site(db, site_id)
    if classe not in CLASSI_ANALISTA or not note.strip():
        return redirect(
            f"/siti/{site.id}?scheda=trust", "Per il giudizio servono una classe e una motivazione.", "errore"
        )
    score = latest_scores(db, site.id).get("piattaforma")
    db.add(
        Revisione(
            tipo="giudizio",
            stato="chiusa",
            sito_id=site.id,
            motivo="Giudizio dell'analista sul sito",
            esito=classe,
            giudizio={
                "classe": classe,
                "classe_automatica": score.classe_rischio if score else None,
                "punteggio_id": score.id if score else None,
                "versione_regole": score.versione_regole if score else None,
            },
            note=note.strip()[:4000],
            assegnata_a=user.id,
            chiusa_da=user.id,
            chiusa_il=utcnow(),
        )
    )
    return redirect(
        f"/siti/{site.id}?scheda=trust", "Giudizio registrato: entra nel campione di validazione."
    )


def automatic_class(score: Punteggio | None) -> str:
    if score is None:
        return "nessun_punteggio"
    if score.classe_rischio:
        return score.classe_rischio
    if score.dettaglio.get("esclusione", "").startswith("Concessionario"):
        return "legale"
    return "nessun_indice"


@router.get("/validazione")
def validation(request: Request, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    judged: dict[int, Revisione] = {}
    for rev in db.execute(
        select(Revisione).where(Revisione.tipo == "giudizio").order_by(Revisione.creata_il.desc())
    ).scalars():
        judged.setdefault(rev.sito_id, rev)
    rows = []
    matrix: Counter[tuple[str, str]] = Counter()
    for site_id, rev in judged.items():
        site = db.get(Sito, site_id)
        score = latest_scores(db, site_id).get("piattaforma")
        auto = automatic_class(score)
        rows.append(
            {
                "sito": site,
                "analista": rev.esito,
                "automatica": auto,
                "giudizio": rev,
                "punteggio": score,
                "concorda": auto == rev.esito,
            }
        )
        matrix[(rev.esito, auto)] += 1
    comparable = [r for r in rows if r["automatica"] not in {"nessun_indice", "nessun_punteggio"}]
    agree = sum(1 for r in comparable if r["concorda"])
    auto_classes = ["basso", "medio", "alto", "legale", "nessun_indice"]
    return render(
        request,
        "validazione.html",
        {
            "sezione": "validazione",
            "revisioni": open_reviews(db),
            "righe": rows,
            "matrice": matrix,
            "classi_analista": list(CLASSI_ANALISTA),
            "classi_auto": auto_classes,
            "obiettivo": OBIETTIVO_VALIDAZIONE,
            "confrontabili": len(comparable),
            "concordi": agree,
            "senza_indice": len(rows) - len(comparable),
            "regole": load_rules(),
        },
    )


@router.get("/siti/{site_id}/report")
def report(
    request: Request,
    site_id: int,
    scarica: int = 0,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    site = _site(db, site_id)
    snaps = (
        db.execute(select(Snapshot).where(Snapshot.sito_id == site.id).order_by(Snapshot.raccolto_il.desc()))
        .scalars()
        .all()
    )
    bets = db.execute(
        select(func.count(), Puntata.fonte).where(Puntata.sito_id == site.id).group_by(Puntata.fonte)
    ).all()
    context = site_context(db, site) | {
        "sito": site,
        "snaps": snaps,
        "gruppi": grouped_indicators(db, site.id),
        "puntate": dict((f, c) for c, f in bets),
        "generato_il": utcnow(),
        "legal_confermate": db.execute(
            select(LegalEntity).where(LegalEntity.sito_id == site.id, LegalEntity.stato == "confermata")
        )
        .scalars()
        .all(),
        "autore": user,
    }
    response = templates.TemplateResponse(request, "report.html", context)
    # Il report è un documento autonomo: stili in linea, nessuno script.
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:"
    )
    if scarica:
        response = Response(
            response.body,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="report-{site.dominio}.html"',
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            },
        )
    return response
