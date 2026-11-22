"""Esecutore dei contenitori di raccolta.

Uso: python -m probes.runner --sonda <nome> [--limite N]

Senza --limite il processo resta in ascolto e rispetta il tetto orario di pagine.
Con --limite si ferma dopo N lavori: è la forma usata da `make collect`.
"""

from __future__ import annotations

import argparse
import logging
import time
import traceback
from collections import deque
from collections.abc import Callable
from typing import Any

from core.collect_client import CollectClient, CollectJob
from core.config import get_settings

log = logging.getLogger("raccolta")

JobRunner = Callable[[CollectClient, CollectJob], dict[str, Any]]


def _snapshot(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from probes.snapshot.collector import run_job

    return run_job(client, job)


def _adm(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from probes.adm.downloader import run_job

    return run_job(client, job)


def _network(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from probes.rete.collector import run_job

    return run_job(client, job)


def _telegram(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from probes.telegram.probe import run_job

    return run_job(client, job)


def _crawl(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from probes.web.probe import run_job

    return run_job(client, job)


def _media(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from extractors.media import run_job

    return run_job(client, job)


def _apk(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from probes.apk.static import run_job

    return run_job(client, job)


def _apk_dynamic(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    from probes.apk.dynamic import run_job

    return run_job(client, job)


# Sonda → tipi di lavoro che esegue.
PROBES: dict[str, dict[str, JobRunner]] = {
    "snapshot": {"snapshot": _snapshot, "rete": _network},
    "adm": {"scarica_adm": _adm},
    "telegram": {"telegram": _telegram},
    "web": {"crawl": _crawl},
    "tor": {"crawl": _crawl},
    "estrazione": {"estrai_media": _media},
    "apk": {"apk": _apk},
    "apk-dinamica": {"apk_dinamica": _apk_dynamic},
}


# Durata della presa di un lavoro: oltre, il lavoro torna in coda. Più lunga per OCR, trascrizione e APK.
LEASES = {"estrazione": 3600, "apk": 1800, "apk-dinamica": 1800, "web": 2700, "tor": 2700, "telegram": 1800}


def cap_payload(job: CollectJob, cap: int | None) -> None:
    """Applica il tetto della prova reale al lavoro preso, qualunque cosa chieda il carico."""
    if not cap:
        return
    payload = job.payload
    if "canali" in payload:
        payload["canali"] = payload["canali"][:cap]
        payload["messaggi_per_canale"] = min(int(payload.get("messaggi_per_canale", 50)), 50)
    if "max_pagine" in payload:
        payload["max_pagine"] = min(int(payload.get("max_pagine", cap)), cap)


def run(
    probe: str,
    limit: int | None,
    client: CollectClient | None = None,
    idle_exit: bool = False,
    cap: int | None = None,
) -> int:
    runners = PROBES[probe]
    client = client or CollectClient()
    per_hour = get_settings().collect_pages_per_hour
    recent: deque[float] = deque()
    done = 0
    while limit is None or done < limit:
        now = time.time()
        while recent and recent[0] < now - 3600:
            recent.popleft()
        if len(recent) >= per_hour:
            time.sleep(5)
            continue
        job = client.claim(list(runners), lease_seconds=LEASES.get(probe, 300))
        if job is None:
            if limit is not None or idle_exit:
                break
            time.sleep(2)
            continue
        recent.append(now)
        cap_payload(job, cap)
        log.info("lavoro %s (%s) preso", job.id, job.kind)
        try:
            result = runners[job.kind](client, job)
            client.close(job.id, True, result)
        except Exception as exc:  # noqa: BLE001 - l'errore si registra, la sonda prosegue
            log.warning("lavoro %s fallito: %s", job.id, exc)
            client.close(job.id, False, error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}")
        done += 1
    return done


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="probes.runner")
    parser.add_argument("--sonda", required=True, choices=sorted(PROBES))
    parser.add_argument("--limite", type=int, default=None, help="numero massimo di lavori")
    parser.add_argument("--tetto", type=int, default=None, help="canali o pagine al massimo per lavoro")
    args = parser.parse_args()
    if args.limite is not None and args.limite < 1:
        parser.error("--limite deve essere almeno 1")
    done = run(args.sonda, args.limite, cap=args.tetto)
    log.info("lavori eseguiti: %s", done)


if __name__ == "__main__":
    main()
