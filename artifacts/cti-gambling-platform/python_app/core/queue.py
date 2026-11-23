"""Coda di lavoro sulla tabella `lavoro`, lato interno.

I contenitori di raccolta non usano questo modulo: chiamano le funzioni SQL
`lavoro_prendi` e `lavoro_chiudi` con il ruolo ristretto (vedi core/collect_client.py).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.models import Lavoro, utcnow

INTERNAL = "interna"
COLLECT = "raccolta"


def enqueue(
    session: Session,
    *,
    queue: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    next_kind: str | None = None,
    site_id: int | None = None,
    user_id: int | None = None,
    origin_id: int | None = None,
    max_attempts: int = 3,
) -> Lavoro:
    job = Lavoro(
        coda=queue,
        tipo=kind,
        carico=payload or {},
        successivo=next_kind,
        sito_id=site_id,
        creato_da=user_id,
        origine_id=origin_id,
        max_tentativi=max_attempts,
    )
    session.add(job)
    session.flush()
    return job


def claim_internal(session: Session, worker: str, lease_seconds: int = 300) -> Lavoro | None:
    """Prende il prossimo lavoro interno. Più lavoratori non si pestano i piedi (SKIP LOCKED)."""
    now = utcnow()
    session.execute(
        text(
            "UPDATE lavoro SET stato = CASE WHEN tentativi >= max_tentativi THEN 'fallito' ELSE 'in_attesa' END, "
            "errore = CASE WHEN tentativi >= max_tentativi THEN 'Scaduto senza esito' ELSE errore END "
            "WHERE coda = 'interna' AND stato = 'in_corso' AND scade_il < :now"
        ),
        {"now": now},
    )
    job = session.execute(
        select(Lavoro)
        .where(Lavoro.coda == INTERNAL, Lavoro.stato == "in_attesa", Lavoro.disponibile_dal <= now)
        .order_by(Lavoro.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.stato = "in_corso"
    job.tentativi += 1
    job.preso_da = worker[:80]
    job.preso_il = now
    job.scade_il = now + timedelta(seconds=lease_seconds)
    session.flush()
    return job


def complete(session: Session, job: Lavoro, result: dict[str, Any] | None = None) -> None:
    job.stato = "completato"
    job.risultato = result or {}
    job.errore = None
    job.chiuso_il = utcnow()
    session.flush()


def fail(session: Session, job: Lavoro, error: str, retry: bool = True) -> None:
    job.errore = error[:4000]
    if retry and job.tentativi < job.max_tentativi:
        job.stato = "in_attesa"
        job.disponibile_dal = utcnow() + timedelta(seconds=30 * job.tentativi)
    else:
        job.stato = "fallito"
        job.chiuso_il = utcnow()
    session.flush()


def retry(session: Session, job: Lavoro) -> Lavoro:
    """Rimette in coda un lavoro fallito come nuovo lavoro, lasciando traccia dell'originale."""
    return enqueue(
        session,
        queue=job.coda,
        kind=job.tipo,
        payload=dict(job.carico),
        next_kind=job.successivo,
        site_id=job.sito_id,
        user_id=job.creato_da,
        origin_id=job.id,
        max_attempts=job.max_tentativi,
    )
