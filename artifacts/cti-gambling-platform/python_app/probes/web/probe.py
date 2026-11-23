"""Esegue il crawler in un sottoprocesso (Scrapy non si riavvia nello stesso processo)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.collect_client import CollectClient, CollectJob

TIMEOUT = 2400


def run_job(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "carico.json", Path(tmp) / "risultato.json"
        src.write_text(json.dumps(job.payload), encoding="utf-8")
        proc = subprocess.run(  # noqa: S603 - comando fisso, nessun input dell'utente nella riga di comando
            [sys.executable, "-m", "probes.web.crawl", str(src), str(dst)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
        if dst.exists():
            manifest = json.loads(dst.read_text(encoding="utf-8")) | {"esito": "riuscito"}
        else:
            manifest = {"esito": "errore", "pagine": [], "errori": [proc.stderr[-2000:]]}
    manifest["raccolto_il"] = datetime.now(UTC).isoformat()
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": manifest["esito"], "pagine": len(manifest["pagine"])}
