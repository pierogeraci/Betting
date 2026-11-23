"""Lettura di una pagina raccolta dal crawler: testo, link esterni, parole chiave, blocchi."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from collectors.base import Page, normalize
from core.domains import registrable_domain
from probes.snapshot.blocks import detect_block

MAX_TEXT = 20_000
MAX_LINKS = 150


def parse_page(url: str, status: int, html: str, words: list[str]) -> dict[str, Any]:
    page = Page(url=url, html=html)
    verdict = detect_block(status, html)
    host = (urlsplit(url).hostname or "").lower()
    base = registrable_domain(host) if host else ""
    internal, external = [], []
    for href, _label in page.links:
        target = urljoin(url, href).split("#")[0]
        parts = urlsplit(target)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            continue
        (internal if registrable_domain(parts.hostname.lower()) == base else external).append(target)
    text = page.text
    low = normalize(text)
    hits = [w for w in words if re.search(r"(?<![a-z0-9])" + re.escape(normalize(w)) + r"(?![a-z0-9])", low)]
    return {
        "url": url,
        "codice_http": status,
        "titolo": (page.parsed and _title(html))[:300],
        "testo": text[:MAX_TEXT],
        "sha256": hashlib.sha256((html or "").encode("utf-8", "replace")).hexdigest(),
        "link_esterni": list(dict.fromkeys(external))[:MAX_LINKS],
        "link_interni": list(dict.fromkeys(internal))[:MAX_LINKS],
        "parole": hits,
        "bloccato": verdict.reason if verdict.blocked else None,
    }


def _title(html: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html or "")
    return " ".join(m.group(1).split()) if m else ""
