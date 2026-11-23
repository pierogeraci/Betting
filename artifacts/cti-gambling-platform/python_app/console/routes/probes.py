"""Fase 2 nel portale: sonde, canali Telegram, parole chiave, avvisi."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from console.deps import Page, admin_user, csrf_protect, current_user, get_db, open_reviews, redirect, render
from core import scheduler
from core.domains import InvalidUrl, normalize_url
from core.models import Avviso, Canale, ElementoGrezzo, ParolaChiave, Sito, Sonda, Utente, utcnow

router = APIRouter()
CHANNEL_RE = re.compile(r"^(?:https?://)?(?:t\.me/|@)?([A-Za-z][A-Za-z0-9_]{3,63})/?$")
FONTI = {"manuale": "Inserimento manuale", "telegram": "Telegram", "web": "Web", "tor": "Tor"}


def unread_alerts(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Avviso).where(Avviso.letto.is_(False))).scalar() or 0


def growth(db: Session, days: int = 14) -> dict:
    """Siti nuovi per giorno e per fonte: il criterio di uscita della Fase 2."""
    since = utcnow() - timedelta(days=days - 1)
    day = func.date_trunc("day", Sito.creato_il)
    rows = db.execute(
        select(day, func.coalesce(Sito.fonte_scoperta, "manuale"), func.count())
        .where(Sito.creato_il >= since.replace(hour=0, minute=0, second=0))
        .group_by(day, Sito.fonte_scoperta)
    ).all()
    dates = [(since + timedelta(days=i)).date() for i in range(days)]
    series = {f: [0] * days for f in FONTI}
    for d, source, count in rows:
        if d.date() in dates:
            series.setdefault(source, [0] * days)[dates.index(d.date())] += count
    totals = [sum(series[f][i] for f in series) for i in range(days)]
    automatic = sum(sum(v) for k, v in series.items() if k != "manuale")
    streak = 0
    for i in range(days - 1, -1, -1):
        if sum(series[f][i] for f in series if f != "manuale"):
            streak += 1
        else:
            break
    return {
        "giorni": dates,
        "serie": series,
        "totali": totals,
        "massimo": max(totals + [1]),
        "automatici": automatic,
        "serie_giorni": streak,
    }


@router.get("/sonde")
def probes(request: Request, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Sonda).order_by(Sonda.id)).scalars().all()
    counts = dict(
        db.execute(select(ElementoGrezzo.sonda_id, func.count()).group_by(ElementoGrezzo.sonda_id)).all()
    )
    return render(
        request,
        "sonde.html",
        {
            "sezione": "sonde",
            "revisioni": open_reviews(db),
            "sonde": rows,
            "conteggi": counts,
            "crescita": growth(db),
            "telegram_acceso": scheduler.telegram_enabled(),
            "canali_attivi": db.execute(
                select(func.count()).select_from(Canale).where(Canale.stato == "attivo")
            ).scalar(),
        },
    )


def _probe(db: Session, probe_id: int) -> Sonda:
    probe = db.get(Sonda, probe_id)
    if probe is None:
        raise HTTPException(404, "Sonda non trovata.")
    return probe


@router.post("/sonde/{probe_id}/stato", dependencies=[Depends(csrf_protect)])
def probe_toggle(probe_id: int, user: Utente = Depends(admin_user), db: Session = Depends(get_db)):
    probe = _probe(db, probe_id)
    if probe.tipo not in scheduler.PROBE_JOBS:
        return redirect("/sonde", "Questa sonda non ha esecuzioni periodiche.", "errore")
    probe.stato = "in_pausa" if probe.stato == "attiva" else "attiva"
    if probe.stato == "attiva":
        probe.ultimo_errore = None
    return redirect("/sonde", f"Sonda {probe.nome} {'attivata' if probe.stato == 'attiva' else 'in pausa'}.")


@router.post("/sonde/{probe_id}/esegui", dependencies=[Depends(csrf_protect)])
def probe_run(probe_id: int, user: Utente = Depends(admin_user), db: Session = Depends(get_db)):
    job, message = scheduler.run_probe(db, _probe(db, probe_id), user.id)
    return redirect("/sonde", message, "ok" if job else "errore")


@router.post("/sonde/{probe_id}/configura", dependencies=[Depends(csrf_protect)])
def probe_configure(
    probe_id: int,
    intervallo_minuti: int = Form(60),
    semi: str = Form(""),
    profondita: int = Form(1),
    max_pagine: int = Form(40),
    max_siti_nuovi: int = Form(30),
    messaggi_per_canale: int = Form(200),
    max_media_mb: int = Form(25),
    scarica_media: str = Form(""),
    user: Utente = Depends(admin_user),
    db: Session = Depends(get_db),
):
    probe = _probe(db, probe_id)
    cfg = dict(probe.configurazione or {})
    cfg["intervallo_minuti"] = max(15, min(intervallo_minuti, 10080))
    cfg["max_siti_nuovi"] = max(0, min(max_siti_nuovi, 200))
    if probe.tipo in {"web", "tor"}:
        seeds, rejected = [], []
        for line in semi.splitlines():
            if not line.strip():
                continue
            try:
                url = normalize_url(line.strip())
            except InvalidUrl as exc:
                rejected.append(f"{line.strip()[:60]}: {exc}")
                continue
            if (probe.tipo == "tor") != url.is_onion:
                rejected.append(
                    f"{url.url}: {'serve un indirizzo .onion' if probe.tipo == 'tor' else 'gli indirizzi .onion vanno nella sonda Tor'}"
                )
                continue
            seeds.append(url.url)
        if rejected:
            return redirect("/sonde", "Semi rifiutati: " + "; ".join(rejected[:3]), "errore")
        cfg.update(
            semi=seeds[:50], profondita=max(0, min(profondita, 2)), max_pagine=max(1, min(max_pagine, 200))
        )
    if probe.tipo == "telegram":
        cfg.update(
            messaggi_per_canale=max(10, min(messaggi_per_canale, 1000)),
            max_media_mb=max(1, min(max_media_mb, 100)),
            scarica_media=bool(scarica_media),
        )
    probe.configurazione = cfg
    return redirect("/sonde", f"Configurazione della sonda {probe.nome} salvata.")


# --- Canali -------------------------------------------------------------------------


@router.get("/canali")
def channels(
    request: Request,
    stato: str = "da_approvare",
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    states = ["da_approvare", "attivo", "in_pausa", "rifiutato", "in_errore"]
    filtro = stato if stato in states else "da_approvare"
    rows = (
        db.execute(select(Canale).where(Canale.stato == filtro).order_by(Canale.creato_il.desc()).limit(300))
        .scalars()
        .all()
    )
    counts = dict(db.execute(select(Canale.stato, func.count()).group_by(Canale.stato)).all())
    return render(
        request,
        "canali.html",
        {
            "sezione": "canali",
            "revisioni": open_reviews(db),
            "righe": rows,
            "filtro": filtro,
            "conteggi": counts,
            "stati": states,
        },
    )


@router.post("/canali", dependencies=[Depends(csrf_protect)])
def channel_add(nome: str = Form(""), user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    m = CHANNEL_RE.match(nome.strip())
    if not m:
        return redirect(
            "/canali",
            "Indica il nome pubblico del canale, per esempio @nomecanale o t.me/nomecanale. I link d'invito non sono ammessi.",
            "errore",
        )
    name = m.group(1).lower()
    db.execute(
        insert(Canale)
        .values(
            piattaforma="telegram",
            identificativo=name,
            stato="da_approvare",
            motivo=f"Aggiunto a mano da {user.nome_utente}",
        )
        .on_conflict_do_nothing()
    )
    return redirect("/canali", f"Canale @{name} aggiunto: approvalo per avviare la raccolta.")


@router.post("/canali/{channel_id}/{azione}", dependencies=[Depends(csrf_protect)])
def channel_action(
    channel_id: int, azione: str, user: Utente = Depends(current_user), db: Session = Depends(get_db)
):
    channel = db.get(Canale, channel_id)
    if channel is None:
        raise HTTPException(404, "Canale non trovato.")
    target = {"approva": "attivo", "rifiuta": "rifiutato", "pausa": "in_pausa", "riattiva": "attivo"}.get(
        azione
    )
    if target is None:
        raise HTTPException(404, "Azione sconosciuta.")
    if target == "rifiutato":
        from core.discovery import erase_channel

        name = channel.identificativo
        erase_channel(db, channel, f"Rifiutato da {user.nome_utente}: nome cancellato")
        return redirect("/canali", f"@{name} rifiutato: il nome è stato cancellato.")
    channel.stato = target
    if target == "attivo":
        channel.approvato_da = user.id
        channel.ultimo_errore = None
    return redirect(
        f"/canali?stato={'da_approvare' if azione in {'approva', 'rifiuta'} else target}",
        f"@{channel.identificativo}: {target.replace('_', ' ')}.",
    )


# --- Parole chiave ------------------------------------------------------------------


@router.get("/parole")
def keywords(request: Request, user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.execute(select(ParolaChiave).order_by(ParolaChiave.categoria, ParolaChiave.termine))
        .scalars()
        .all()
    )
    return render(request, "parole.html", {"sezione": "parole", "revisioni": open_reviews(db), "righe": rows})


@router.post("/parole", dependencies=[Depends(csrf_protect)])
def keyword_add(
    termine: str = Form(""),
    categoria: str = Form("gioco"),
    lingua: str = Form("it"),
    avviso: str = Form(""),
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    term = " ".join(termine.split()).lower()[:120]
    if len(term) < 2:
        return redirect("/parole", "La parola chiave deve avere almeno due caratteri.", "errore")
    db.execute(
        insert(ParolaChiave)
        .values(
            termine=term,
            categoria=categoria[:40] or "gioco",
            lingua=lingua[:10] or "it",
            avviso=bool(avviso),
            creato_da=user.id,
        )
        .on_conflict_do_nothing()
    )
    return redirect("/parole", f"Parola chiave «{term}» aggiunta.")


@router.post("/parole/{kw_id}/{azione}", dependencies=[Depends(csrf_protect)])
def keyword_action(
    kw_id: int, azione: str, user: Utente = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.get(ParolaChiave, kw_id)
    if row is None:
        raise HTTPException(404, "Parola chiave non trovata.")
    if azione == "attiva":
        row.attiva = not row.attiva
    elif azione == "avviso":
        row.avviso = not row.avviso
    elif azione == "elimina":
        db.delete(row)
    else:
        raise HTTPException(404, "Azione sconosciuta.")
    return redirect("/parole", "Parola chiave aggiornata.")


# --- Avvisi -------------------------------------------------------------------------


@router.get("/avvisi")
def alerts(
    request: Request,
    tutti: int = 0,
    pagina: int = 1,
    user: Utente = Depends(current_user),
    db: Session = Depends(get_db),
):
    cond = [] if tutti else [Avviso.letto.is_(False)]
    page = Page(pagina, db.execute(select(func.count()).select_from(Avviso).where(*cond)).scalar() or 0)
    rows = (
        db.execute(
            select(Avviso).where(*cond).order_by(Avviso.creato_il.desc()).offset(page.offset).limit(page.size)
        )
        .scalars()
        .all()
    )
    return render(
        request,
        "avvisi.html",
        {"sezione": "avvisi", "revisioni": open_reviews(db), "righe": rows, "tutti": tutti, "pag": page},
    )


@router.post("/avvisi/letti", dependencies=[Depends(csrf_protect)])
def alerts_read(ids: str = Form(""), user: Utente = Depends(current_user), db: Session = Depends(get_db)):
    query = Avviso.__table__.update().where(Avviso.letto.is_(False))
    chosen = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if chosen:
        query = query.where(Avviso.id.in_(chosen))
    db.execute(query.values(letto=True, letto_da=user.id))
    return redirect("/avvisi", "Avvisi segnati come letti.")
