"""Lavoratore interno: esegue i lavori della coda `interna`.

Uso: python -m core.worker [--una-volta]
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import adm, ingest, queue
from core.db import session_scope
from core.models import Lavoro, Sito

log = logging.getLogger("lavoratore")

Handler = Callable[[Session, Lavoro], dict[str, Any] | None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(func: Handler) -> Handler:
        HANDLERS[kind] = func
        return func

    return register


def _origin(session: Session, job: Lavoro) -> Lavoro:
    origin = session.get(Lavoro, job.carico.get("lavoro_origine"))
    if origin is None:
        raise ingest.IngestError("Lavoro di origine non trovato")
    return origin


@handler("acquisisci_snapshot")
def _ingest_snapshot(session: Session, job: Lavoro) -> dict[str, Any]:
    snapshot = ingest.ingest_snapshot(session, _origin(session, job))
    return {"snapshot_id": snapshot.id, "stato": snapshot.stato}


@handler("acquisisci_adm")
def _ingest_adm(session: Session, job: Lavoro) -> dict[str, Any]:
    return ingest.ingest_adm(session, _origin(session, job))


@handler("acquisisci_rete")
def _ingest_network(session: Session, job: Lavoro) -> dict[str, Any]:
    return ingest.ingest_network(session, _origin(session, job))


@handler("acquisisci_telegram")
def _ingest_telegram(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.ingest_probes import ingest_telegram

    return ingest_telegram(session, _origin(session, job))


@handler("acquisisci_crawl")
def _ingest_crawl(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.ingest_probes import ingest_crawl

    return ingest_crawl(session, _origin(session, job))


@handler("acquisisci_estrazione")
def _ingest_extraction(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.media_jobs import ingest_extraction

    return ingest_extraction(session, _origin(session, job))


@handler("analizza_testo")
def _analyse(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.analysis import analyse_element
    from core.models import ElementoGrezzo

    element = session.get(ElementoGrezzo, job.carico.get("elemento_id"))
    if element is None:
        return {"saltato": "elemento non trovato"}
    return analyse_element(session, element)


@handler("addestra_classificatore")
def _train(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.analysis import train_classifier

    return train_classifier(session, job.creato_da)


@handler("argomenti")
def _topics(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.analysis import compute_topics

    return compute_topics(session)


@handler("valuta_entita")
def _eval_entities(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.analysis import evaluate_entities

    return evaluate_entities(session)


@handler("acquisisci_apk")
def _ingest_apk(session: Session, job: Lavoro) -> dict[str, Any]:
    from core.apk import ingest_apk

    return ingest_apk(session, _origin(session, job))


@handler("profila")
def _profile(session: Session, job: Lavoro) -> dict[str, Any]:
    from core import profiling

    site = session.get(Sito, job.carico.get("sito_id"))
    if site is None:
        return {"saltato": "sito non trovato"}
    return profiling.profile_site(session, site)


@handler("punteggio")
def _score(session: Session, job: Lavoro) -> dict[str, Any]:
    from core import profiling

    site = session.get(Sito, job.carico.get("sito_id"))
    if site is None:
        return {"saltato": "sito non trovato"}
    rows = profiling.score_site(session, site)
    return {"punteggi": len(rows), "classe": rows[0].classe_rischio}


@handler("confronto_adm")
def _compare(session: Session, job: Lavoro) -> dict[str, Any]:
    site = session.get(Sito, job.carico.get("sito_id"))
    if site is None:
        return {"saltato": "sito non trovato"}
    before = site.esito_adm
    adm.compare_site(session, site)
    if (
        before != site.esito_adm
        and session.execute(
            select(Lavoro.id).where(Lavoro.sito_id == site.id, Lavoro.tipo == "profila")
        ).first()
    ):
        # L'esito ADM entra nelle regole del Trust Index: si ricalcola.
        queue.enqueue(
            session, queue=queue.INTERNAL, kind="punteggio", payload={"sito_id": site.id}, site_id=site.id
        )
    return {"esito_adm": site.esito_adm}


@handler("confronto_adm_tutti")
def _compare_all(session: Session, job: Lavoro) -> dict[str, Any]:
    count = 0
    for site in session.execute(select(Sito)).scalars():
        adm.compare_site(session, site)
        count += 1
    return {"siti": count}


def run_one(worker: str) -> bool:
    """Esegue al più un lavoro. Restituisce False se la coda è vuota."""
    with session_scope() as session:
        job = queue.claim_internal(session, worker)
        if job is None:
            return False
        job_id, kind = job.id, job.tipo
    try:
        with session_scope() as session:
            job = session.get(Lavoro, job_id)
            func = HANDLERS.get(kind)
            if func is None:
                queue.fail(session, job, f"Tipo di lavoro sconosciuto: {kind}", retry=False)
                return True
            result = func(session, job)
            queue.complete(session, job, result)
    except Exception as exc:  # noqa: BLE001 - un lavoro che fallisce non ferma gli altri
        log.warning("lavoro %s (%s) fallito: %s", job_id, kind, exc)
        with session_scope() as session:
            job = session.get(Lavoro, job_id)
            detail = f"{type(exc).__name__}: {exc}"
            if not isinstance(exc, ingest.IngestError | adm.UnsupportedList):
                detail += "\n" + traceback.format_exc(limit=5)
            queue.fail(
                session, job, detail, retry=not isinstance(exc, ingest.IngestError | adm.UnsupportedList)
            )
    return True


def drain(worker: str = "prova") -> int:
    """Svuota la coda interna. Usata dai test e dalle prove."""
    count = 0
    while run_one(worker):
        count += 1
    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    worker = f"{socket.gethostname()}:{os.getpid()}"
    once = "--una-volta" in sys.argv
    log.info("lavoratore interno avviato (%s)", worker)
    last_tick = 0.0
    while True:
        if time.time() - last_tick > 60:
            last_tick = time.time()
            try:
                from core import scheduler

                with session_scope() as session:
                    started = scheduler.tick(session)
                if started:
                    log.info("sonde avviate: %s", ", ".join(started))
            except Exception as exc:  # noqa: BLE001 - il pianificatore non deve fermare il lavoratore
                log.warning("pianificatore: %s", exc)
        if not run_one(worker):
            if once:
                return
            time.sleep(1.0)


if __name__ == "__main__":
    main()
