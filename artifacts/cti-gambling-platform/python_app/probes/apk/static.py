"""Analisi statica di un APK con MobSF, nel contenitore di analisi delle app.

L'APK non si esegue: MobSF lo decompila e ne legge manifesto, permessi, librerie,
URL e domini nel codice, certificato di firma. Lavora su rete separata.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib import request as urlrequest

MOBSF_URL = os.environ.get("MOBSF_URL", "http://mobsf:8000")
DANGEROUS = "dangerous"
AD_HINTS = re.compile(
    r"(?i)ads?|admob|applovin|unity3d\.ads|ironsource|vungle|chartboost|mopub|startapp|inmobi|appsflyer|adjust|branch|facebook\.ads|mintegral|pangle|bytedance"
)
SDK_DOMAINS = {
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "googlesyndication.com",
    "doubleclick.net",
    "firebaseio.com",
    "crashlytics.com",
    "facebook.com",
    "fbcdn.net",
    "android.com",
    "apple.com",
    "appsflyer.com",
    "adjust.com",
    "branch.io",
    "unity3d.com",
    "applovin.com",
    "w3.org",
    "schemas.android.com",
    "xmlpull.org",
    "apache.org",
    "github.com",
    "mozilla.org",
    "jquery.com",
    "example.com",
    "googleusercontent.com",
    "app-measurement.com",
    "onesignal.com",
    "sentry.io",
}


def _post(path: str, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
    req = urlrequest.Request(
        MOBSF_URL + path, data=data, headers=headers | {"Authorization": os.environ.get("MOBSF_API_KEY", "")}
    )  # noqa: S310
    with urlrequest.urlopen(req, timeout=900) as response:  # noqa: S310 - servizio MobSF sulla rete di analisi
        return json.loads(response.read())


def _multipart(name: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----betting" + os.urandom(8).hex()
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def scan(apk: bytes, name: str) -> dict[str, Any]:
    body, ctype = _multipart(name, apk)
    upload = _post("/api/v1/upload", body, {"Content-Type": ctype})
    form = f"hash={upload['hash']}".encode()
    _post("/api/v1/scan", form, {"Content-Type": "application/x-www-form-urlencoded"})
    return _post("/api/v1/report_json", form, {"Content-Type": "application/x-www-form-urlencoded"})


def registrable(host: str) -> str:
    parts = host.lower().strip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


COMPANY_FORM = re.compile(
    r"(?i)\b(s\.?p\.?a|s\.?r\.?l|ltd|limited|n\.?v|b\.?v|gmbh|llc|s\.?a|inc|corp|plc|o[uü]|sia|s\.?l)\b"
)


def company_subject(subject: str) -> str | None:
    """Del soggetto del certificato restano solo organizzazione e paese, e solo se è una società:
    CN ed email spesso sono il nome di uno sviluppatore."""
    parts = dict(re.findall(r"(?:^|,\s*)(O|C)=([^,]+)", subject or ""))
    org = parts.get("O", "").strip()
    if not org or not COMPANY_FORM.search(org):
        return None
    return f"O={org[:200]}" + (f", C={parts['C'].strip()[:4]}" if parts.get("C") else "")


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    """Riassunto del rapporto MobSF: solo ciò che serve a collegare l'app ai siti e all'operatore."""
    permissions = report.get("permissions") or {}
    dangerous = sorted(
        p for p, info in permissions.items() if isinstance(info, dict) and info.get("status") == DANGEROUS
    )
    libraries = report.get("libraries") or report.get("trackers", {}).get("trackers") or []
    names = []
    for lib in libraries:
        names.append(lib.get("name") if isinstance(lib, dict) else str(lib))
    trackers = [
        t.get("name") for t in (report.get("trackers") or {}).get("trackers", []) if isinstance(t, dict)
    ]
    ads = sorted({n for n in names + trackers if n and AD_HINTS.search(n)})
    domains = sorted({registrable(d) for d in (report.get("domains") or {}) if d})
    candidate = [d for d in domains if d not in SDK_DOMAINS]
    urls = [u.get("urls", [u])[0] if isinstance(u, dict) else str(u) for u in (report.get("urls") or [])][
        :200
    ]
    cert = report.get("certificate_analysis") or {}
    cert_info = cert.get("certificate_info", "") if isinstance(cert, dict) else ""
    sha256 = re.search(r"(?i)sha256 Digest:\s*([0-9a-f]{64})", cert_info or "")
    subject = re.search(r"(?i)X\.509 Subject:\s*([^\n]+)", cert_info or "")
    return {
        "pacchetto": report.get("package_name"),
        "nome_app": report.get("app_name"),
        "versione": report.get("version_name"),
        "sdk_minimo": report.get("min_sdk"),
        "sdk_target": report.get("target_sdk"),
        "sha256_apk": report.get("sha256"),
        "permessi_pericolosi": dangerous,
        "permessi_totali": len(permissions),
        "librerie_pubblicitarie": ads,
        "tracker": sorted(t for t in trackers if t),
        "domini": domains[:300],
        "domini_candidati": candidate[:100],
        "url": urls,
        "certificato": {
            "sha256": sha256.group(1).lower() if sha256 else None,
            "soggetto": company_subject(subject.group(1) if subject else ""),
        },
        "attivita": len(report.get("activities") or []),
        "servizi": len(report.get("services") or []),
        "punteggio_sicurezza": (report.get("appsec") or {}).get("security_score"),
    }


def run_job(client: Any, job: Any) -> dict[str, Any]:
    data = client.read_work(str(job.payload.get("chiave", "")))
    manifest: dict[str, Any] = {
        "raccolto_il": datetime.now(UTC).isoformat(),
        "media_id": job.payload.get("media_id"),
    }
    if data[:2] != b"PK":
        manifest |= {"esito": "errore", "errore": "Il file non è un APK (archivio ZIP)"}
    else:
        try:
            manifest |= {"esito": "riuscito", "apk": summarize(scan(data, "app.apk")), "strumento": "MobSF"}
        except Exception as exc:  # noqa: BLE001
            manifest |= {"esito": "errore", "errore": f"MobSF: {type(exc).__name__}: {str(exc)[:300]}"}
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": manifest["esito"]}
