"""Analisi dinamica di un APK: emulatore Android usa e getta e proxy di intercettazione.

Gira solo nel profilo `apk-dinamica`, con un emulatore che si ricrea a ogni analisi
su una rete interna: l'unica uscita è mitmproxy, che non vede la rete di raccolta.
L'app viene installata e soltanto avviata (attività principale), poi osservata in modo
passivo per un tempo fisso: nessun tocco o testo casuale, che potrebbe compilare moduli
o premere un pulsante di deposito. mitmproxy registra solo indirizzi e metadati e blocca
ogni invio di dati verso domini che non sono librerie note.
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
DURATA_S = int(os.environ.get("DURATA_ANALISI_S", "300"))


def adb(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - binario fisso, argomenti costruiti qui
        [ADB, "-s", EMULATOR, *args], capture_output=True, text=True, timeout=timeout, check=False
    )


def flows_summary(lines: list[str], since: float) -> dict[str, Any]:
    """Domini contattati dall'app e invii bloccati (righe JSON scritte dallo script di mitmproxy)."""
    hosts: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    blocked: Counter[str] = Counter()
    for line in lines:
        try:
            flow = json.loads(line)
        except ValueError:
            continue
        if float(flow.get("t", 0)) < since:
            continue
        host = (urlsplit(str(flow.get("url", ""))).hostname or "").lower()
        if not host:
            continue
        if flow.get("bloccato"):
            blocked[host] += 1
            continue
        hosts[host] += 1
        sizes[host] += int(flow.get("byte", 0) or 0)
    return {
        "richieste": sum(hosts.values()),
        "domini": [{"host": h, "richieste": c, "byte": sizes[h]} for h, c in hosts.most_common(200)],
        "invii_bloccati": [{"host": h, "tentativi": c} for h, c in blocked.most_common(50)],
    }


def run_job(client: Any, job: Any) -> dict[str, Any]:
    data = client.read_work(str(job.payload.get("chiave", "")))
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
            # Solo l'avvio dell'attività principale, poi osservazione passiva.
            steps.append(adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"))
            time.sleep(DURATA_S)
            steps.append(adb("shell", "am", "force-stop", package))
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
