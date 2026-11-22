"""Snapshot di una sola pagina pubblica.

Regole: una pagina per lavoro, nessun modulo compilato, nessun accesso, nessun
download. Il browser si dichiara per quello che è: nessun mascheramento. Se la
pagina è una barriera lo si registra e ci si ferma.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.collect_client import CollectClient, CollectJob
from core.config import get_settings
from core.domains import InvalidUrl, normalize_url
from probes.snapshot.blocks import detect_block
from probes.snapshot.guard import url_allowed

TOOL = "playwright-chromium"
NAV_TIMEOUT_MS = 45_000
SETTLE_TIMEOUT_MS = 8_000
MAX_HTML_BYTES = 5_000_000
MAX_SHOT_HEIGHT = 6000
VIEWPORT = {"width": 1366, "height": 900}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redirect_chain(response: Any) -> list[dict[str, Any]]:
    """Catena dei reindirizzamenti HTTP, dal primo URL all'ultimo."""
    chain: list[dict[str, Any]] = []
    request = response.request if response is not None else None
    while request is not None:
        resp = request.response()
        chain.append({"url": request.url, "codice": resp.status if resp else None})
        request = request.redirected_from
    chain.reverse()
    return chain


def build_manifest(
    *,
    state: str,
    requested: str,
    files: dict[str, bytes],
    final_url: str | None = None,
    status: int | None = None,
    title: str | None = None,
    chain: list[dict[str, Any]] | None = None,
    reason: str | None = None,
    excerpt: str | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    names = {"html": "pagina.html", "schermata": "schermata.png", "traffico": "traffico.har"}
    manifest: dict[str, Any] = {
        "esito": state,
        "url_richiesto": requested,
        "url_finale": final_url,
        "codice_http": status,
        "titolo": title,
        "reindirizzamenti": chain or [],
        "motivo": reason,
        "estratto_blocco": excerpt,
        "errore": error,
        "raccolto_il": datetime.now(UTC).isoformat(),
        "strumento": TOOL,
        "file": {
            k: {"nome": names[k], "sha256": _sha(v), "dimensione": len(v)} for k, v in files.items() if v
        },
    }
    manifest.update(extra or {})
    return manifest


def capture(url: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Apre la pagina e restituisce (manifesto, file). Non solleva per errori del sito."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    settings = get_settings()
    started = time.monotonic()
    files: dict[str, bytes] = {}
    blocked_requests = 0
    info: dict[str, Any] = {"rete_intercettata": settings.intercepted_network}
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
        har_path = Path(tmp) / "traffico.har"
        launch: dict[str, Any] = {"headless": True}
        if settings.collect_proxy:
            launch["proxy"] = {"server": settings.collect_proxy}
        browser = pw.chromium.launch(**launch)
        info["versione_strumento"] = f"{browser.version}"
        context = browser.new_context(
            viewport=VIEWPORT,
            locale="it-IT",
            accept_downloads=False,
            service_workers="block",
            record_har_path=str(har_path),
            record_har_content="omit",
            # Solo quando un proxy di sessione sostituisce i certificati: in quel caso
            # le evidenze sul certificato sono marcate come non valide.
            ignore_https_errors=settings.intercepted_network,
        )
        page = context.new_page()
        info["user_agent"] = page.evaluate("navigator.userAgent")

        def route_handler(route: Any) -> None:
            nonlocal blocked_requests
            if url_allowed(route.request.url):
                route.continue_()
            else:
                blocked_requests += 1
                route.abort("blockedbyclient")

        page.route("**/*", route_handler)
        state, error, response = "riuscito", None, None
        try:
            response = page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            except PlaywrightError:
                pass
        except PlaywrightError as exc:
            state, error = "errore", str(exc).splitlines()[0][:500]
        html, title, final_url, status = "", None, None, None
        if state == "riuscito":
            try:
                html = page.content()
                title = page.title()
                final_url = page.url
                status = response.status if response is not None else None
                height = min(
                    MAX_SHOT_HEIGHT,
                    int(page.evaluate("document.documentElement.scrollHeight") or VIEWPORT["height"]),
                )
                files["schermata"] = page.screenshot(
                    clip={
                        "x": 0,
                        "y": 0,
                        "width": VIEWPORT["width"],
                        "height": max(height, VIEWPORT["height"]),
                    },
                    full_page=True,
                    type="png",
                )
            except PlaywrightError as exc:
                state, error = "errore", str(exc).splitlines()[0][:500]
        chain = redirect_chain(response) if response is not None else []
        context.close()
        browser.close()
        if har_path.exists():
            files["traffico"] = har_path.read_bytes()
    raw_html = html.encode("utf-8", "replace")
    if len(raw_html) > MAX_HTML_BYTES:
        raw_html = raw_html[:MAX_HTML_BYTES]
        info["html_troncato"] = True
    if raw_html:
        files["html"] = raw_html
    reason = excerpt = None
    if state == "riuscito":
        verdict = detect_block(status, html)
        if verdict.blocked:
            state, reason, excerpt = "bloccato", verdict.reason, verdict.excerpt
    info["durata_ms"] = int((time.monotonic() - started) * 1000)
    info["richieste_bloccate"] = blocked_requests
    manifest = build_manifest(
        state=state,
        requested=url,
        files=files,
        final_url=final_url,
        status=status,
        title=title,
        chain=chain,
        reason=reason,
        excerpt=excerpt,
        error=error,
        extra=info,
    )
    return manifest, files


def run_job(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    """Esegue un lavoro `snapshot` e lascia manifesto e file nel secchio di arrivo."""
    raw = str(job.payload.get("url", ""))
    try:
        url = normalize_url(raw).url
    except InvalidUrl as exc:
        manifest, files = (
            build_manifest(state="errore", requested=raw, files={}, error=f"URL rifiutato: {exc}"),
            {},
        )
    else:
        if not url_allowed(url):
            manifest, files = (
                build_manifest(
                    state="errore", requested=url, files={}, error="L'URL punta a un indirizzo non pubblico"
                ),
                {},
            )
        else:
            manifest, files = capture(url)
    types = {"html": "text/html", "schermata": "image/png", "traffico": "application/json"}
    for key, data in files.items():
        client.upload(job.id, manifest["file"][key]["nome"], data, types[key])
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": manifest["esito"], "motivo": manifest.get("motivo")}
