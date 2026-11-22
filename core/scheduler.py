"""Pianificatore delle sonde: mette in coda le esecuzioni periodiche.

Gira dentro il lavoratore interno. Una sonda parte se è attiva, se non ha già un
lavoro in coda, se è passato l'intervallo configurato e se il servizio non ha
chiesto di attendere (`disponibile_dal`).
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import queue
from core.keywords import active_keywords
from core.models import Canale, Lavoro, Sonda, utcnow

PROBE_JOBS = {
    "telegram": ("telegram", "acquisisci_telegram"),
    "web": ("crawl", "acquisisci_crawl"),
    "tor": ("crawl", "acquisisci_crawl"),
}


def telegram_enabled() -> bool:
    return os.environ.get("TELEGRAM_PROBE_ENABLED", "true").strip().lower() not in {"false", "0", "no"}


def build_payload(session: Session, probe: Sonda) -> dict[str, Any] | None:
    cfg = probe.configurazione or {}
    words = [k.term for k in active_keywords(session)]
    if probe.tipo == "telegram":
        channels = (
            session.execute(
                select(Canale)
                .where(Canale.piattaforma == "telegram", Canale.stato == "attivo")
                .order_by(Canale.id)
            )
            .scalars()
            .all()
        )
        if not channels:
            return None
        return {
            "sonda_id": probe.id,
            "canali": [
                {"id": c.id, "nome": c.identificativo, "cursore": int(c.cursore or 0)} for c in channels
            ],
            "parole": words,
            "messaggi_per_canale": int(cfg.get("messaggi_per_canale", 200)),
            "scarica_media": bool(cfg.get("scarica_media", True)),
            "max_media_mb": int(cfg.get("max_media_mb", 25)),
        }
    if probe.tipo in {"web", "tor"}:
        seeds = [s for s in cfg.get("semi", []) if s]
        if not seeds:
            return None
        return {
            "sonda_id": probe.id,
            "semi": seeds[:50],
            "tor": probe.tipo == "tor",
            "parole": words,
            "profondita": min(int(cfg.get("profondita", 1)), 2),
            "max_pagine": min(int(cfg.get("max_pagine", 40)), 200),
        }
    return None


def run_probe(
    session: Session, probe: Sonda, user_id: int | None = None, force: bool = False
) -> tuple[Lavoro | None, str]:
    """Mette in coda un'esecuzione della sonda. Restituisce (lavoro, messaggio per l'analista)."""
    if probe.tipo not in PROBE_JOBS:
        return None, "Questa sonda non si esegue a intervalli."
    if probe.tipo == "telegram" and not telegram_enabled():
        return None, "La sonda Telegram è spenta (TELEGRAM_PROBE_ENABLED=false)."
    now = utcnow()
    if probe.disponibile_dal and probe.disponibile_dal > now:
        return None, f"Il servizio ha chiesto di attendere fino alle {probe.disponibile_dal:%H:%M} UTC."
    kind, follow = PROBE_JOBS[probe.tipo]
    pending = session.execute(
        select(Lavoro.id).where(
            Lavoro.tipo == kind,
            Lavoro.carico["sonda_id"].astext == str(probe.id),
            Lavoro.stato.in_(["in_attesa", "in_corso"]),
        )
    ).first()
    if pending:
        return None, "C'è già un'esecuzione in coda."
    payload = build_payload(session, probe)
    if payload is None:
        what = "canali attivi" if probe.tipo == "telegram" else "semi"
        return None, f"Nessun {what} configurato."
    job = queue.enqueue(
        session,
        queue=queue.COLLECT,
        kind=kind,
        payload=payload,
        next_kind=follow,
        user_id=user_id,
        max_attempts=1,
    )
    probe.ultima_esecuzione = now
    return job, "Esecuzione messa in coda."


def tick(session: Session) -> list[str]:
    """Controlla tutte le sonde attive e mette in coda quelle dovute."""
    started = []
    now = utcnow()
    for probe in session.execute(
        select(Sonda).where(Sonda.stato == "attiva", Sonda.tipo.in_(list(PROBE_JOBS)))
    ).scalars():
        interval = timedelta(minutes=max(5, int((probe.configurazione or {}).get("intervallo_minuti", 60))))
        if probe.ultima_esecuzione and probe.ultima_esecuzione + interval > now:
            continue
        job, _ = run_probe(session, probe)
        if job:
            started.append(probe.nome)
    return started
