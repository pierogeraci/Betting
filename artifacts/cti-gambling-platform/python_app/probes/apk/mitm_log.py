"""Script di mitmproxy per l'analisi dinamica degli APK.

Registra solo metodo, indirizzo, codice e dimensione di ogni richiesta (nessun corpo).
Blocca ogni invio di dati (POST, PUT, PATCH con corpo) verso domini che non sono librerie
note: l'app non deve poter registrare account, inviare moduli o avviare pagamenti.
"""

import json
import os
import time

PATH = os.environ.get("FLUSSI_MITM", "/flussi/flussi.jsonl")
SDK = (
    "googleapis.com",
    "google.com",
    "gstatic.com",
    "firebaseio.com",
    "crashlytics.com",
    "app-measurement.com",
    "appsflyer.com",
    "adjust.com",
    "facebook.com",
    "doubleclick.net",
    "googlesyndication.com",
    "unity3d.com",
    "applovin.com",
)


def _write(record):
    with open(PATH, "a", encoding="utf-8") as handle:  # noqa: PTH123
        handle.write(json.dumps(record) + "\n")


def request(flow):  # chiamata da mitmproxy prima di inoltrare la richiesta
    host = flow.request.pretty_host.lower()
    sends_data = flow.request.method in {"POST", "PUT", "PATCH"} and len(flow.request.raw_content or b"") > 0
    if sends_data and not any(host == d or host.endswith("." + d) for d in SDK):
        from mitmproxy import http

        flow.response = http.Response.make(403, b"", {"Content-Type": "text/plain"})
        flow.metadata["bloccato"] = True
        _write(
            {
                "t": time.time(),
                "metodo": flow.request.method,
                "url": flow.request.pretty_url,
                "codice": 403,
                "byte": 0,
                "bloccato": True,
            }
        )


def response(flow):  # chiamata da mitmproxy a risposta ricevuta
    if flow.metadata.get("bloccato"):
        return
    _write(
        {
            "t": time.time(),
            "metodo": flow.request.method,
            "url": flow.request.pretty_url,
            "codice": flow.response.status_code,
            "byte": len(flow.response.raw_content or b""),
        }
    )
