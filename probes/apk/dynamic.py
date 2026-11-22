"""Analisi dinamica di un APK: emulatore Android ufficiale usa e getta e proxy di intercettazione.

Gira solo nel profilo `apk-dinamica`, su rete separata, con un emulatore che si
ricrea a ogni analisi. L'app viene installata, avviata e stimolata con eventi
casuali (monkey) per un tempo fisso; il traffico verso i servizi pubblicitari e i
siti di gioco passa da mitmproxy, che ne registra solo indirizzi e metadati.
Non si inseriscono credenziali, non si creano account, non si fanno pagamenti.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ADB = os.environ.get("ADB", "adb")
EMULATOR = os.environ.get("EMULATORE", "emulatore:5555")
FLOWS = Path(os.environ.get("FLUSSI_MITM", "/flussi/flussi.jsonl"))
DURATA_S = int(os.environ.get("DURATA_ANALISI_S", "600"))


def adb(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [ADB, "-s", EMULATOR, *args], capture_output=True, text=True, timeout=timeout, check=False
    )  # noqa: S603


def flows_summary(lines: list[str], since: float) -> dict[str, Any]:
    """Domini contattati dall'app (righe JSON scritte dallo script di mitmproxy)."""
    hosts: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for line in lines:
        try:
            flow = json.loads(line)
        except ValueError:
            continue
        if float(flow.get("t", 0)) < since:
            continue
        host = (urlsplit(str(flow.get("url", ""))).hostname or "").lower()
        if host:
            hosts[host] += 1
            sizes[host] += int(flow.get("byte", 0) or 0)
    return {
        "richieste": sum(hosts.values()),
        "domini": [{"host": h, "richieste": c, "byte": sizes[h]} for h, c in hosts.most_common(200)],
    }


def run_job(client: Any, job: Any) -> dict[str, Any]:
    from core.config import get_settings

    data = client.reader().get(get_settings().s3_work_bucket, str(job.payload.get("chiave", "")))
    manifest: dict[str, Any] = {
        "raccolto_il": datetime.now(UTC).isoformat(),
        "media_id": job.payload.get("media_id"),
    }
    package = str(job.payload.get("pacchetto") or "")
    with tempfile.TemporaryDirectory() as tmp:
        apk = Path(tmp) / "app.apk"
        apk.write_bytes(data)
        started = time.time()
        steps = [adb("install", "-r", "-g", str(apk), timeout=300)]
        if package:
            steps.append(
                adb(
                    "shell",
                    "monkey",
                    "-p",
                    package,
                    "--throttle",
                    "500",
                    "-s",
                    "42",
                    str(DURATA_S * 2),
                    timeout=DURATA_S + 120,
                )
            )
            steps.append(adb("uninstall", package))
        errors = [s.stderr.strip()[:300] for s in steps if s.returncode != 0]
    lines = FLOWS.read_text(encoding="utf-8").splitlines() if FLOWS.exists() else []
    manifest |= {
        "esito": "riuscito" if not errors else "errore",
        "errori": errors,
        "traffico": flows_summary(lines, started),
        "durata_s": int(time.time() - started),
    }
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": manifest["esito"]}
