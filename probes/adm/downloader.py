"""Scarica un elenco ADM dal portale ufficiale. Un file per lavoro, senza autenticazione."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from core.collect_client import CollectClient, CollectJob

MAX_BYTES = 50_000_000
TIMEOUT = 60
USER_AGENT = "betting-antifrode/0.1 (lettura elenchi pubblici ADM)"


def fetch(url: str) -> tuple[dict[str, Any], bytes]:
    info: dict[str, Any] = {
        "url_richiesto": url,
        "raccolto_il": datetime.now(UTC).isoformat(),
        "strumento": "urllib",
    }
    if urlsplit(url).scheme != "https":
        return info | {"esito": "errore", "errore": "È ammesso solo https"}, b""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - schema verificato sopra
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            data = response.read(MAX_BYTES + 1)
            info |= {
                "url_finale": response.geturl(),
                "codice_http": response.status,
                "tipo": response.headers.get("Content-Type"),
            }
    except urllib.error.HTTPError as exc:
        return info | {"esito": "errore", "codice_http": exc.code, "errore": f"HTTP {exc.code}"}, b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return info | {"esito": "errore", "errore": str(exc)[:300]}, b""
    if len(data) > MAX_BYTES:
        return info | {"esito": "errore", "errore": "File troppo grande"}, b""
    if not data:
        return info | {"esito": "errore", "errore": "File vuoto"}, b""
    return info | {"esito": "riuscito"}, data


def run_job(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    manifest, data = fetch(str(job.payload.get("url", "")))
    if data:
        name = "elenco.dat"
        manifest["file"] = {
            "elenco": {"nome": name, "sha256": hashlib.sha256(data).hexdigest(), "dimensione": len(data)}
        }
        client.upload(job.id, name, data)
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": manifest["esito"], "errore": manifest.get("errore")}
