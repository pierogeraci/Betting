"""Riconoscimento del tipo di pagina, per sapere dove un dato dovrebbe trovarsi."""

from __future__ import annotations

import re

from collectors.base import Page, normalize

KINDS = {
    "termini": r"termini|condizioni|terms|conditions|t-c|tos|regolamento|rules|agb",
    "pagamenti": r"pagament|payment|deposit|prelievi|withdraw|cassa|cashier|banking|metodi",
    "registrazione": r"registra|iscri|sign-?up|register|join|crea-account|open-account",
    "faq": r"faq|aiuto|help|support|assistenza|domande",
    "chi_siamo": r"chi-siamo|about|azienda|company|impressum|contatti|contact",
    "privacy": r"privacy|cookie",
    "gioco_responsabile": r"responsab|responsible",
    "licenza": r"licen|license|licence|regulat",
}


def page_kind(page: Page) -> str:
    target = normalize(page.url + " " + (page.title or ""))
    for kind, pattern in KINDS.items():
        if re.search(pattern, target):
            return kind
    return "home"


def links_to_profile(page: Page, limit: int = 6) -> list[str]:
    """Link pubblici dello stesso sito che conviene fotografare per la profilazione."""
    from core.domains import registrable_domain

    base = registrable_domain(page.host) if page.host else ""
    wanted: dict[str, str] = {}
    for href, label in page.links:
        from urllib.parse import urlsplit

        parts = urlsplit(href)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            continue
        if registrable_domain(parts.hostname.lower()) != base:
            continue
        target = normalize(href + " " + label)
        for kind, pattern in KINDS.items():
            if kind in wanted or kind in {"privacy"}:
                continue
            if re.search(pattern, target):
                wanted[kind] = href.split("#")[0]
                break
        if len(wanted) >= limit:
            break
    return list(dict.fromkeys(wanted.values()))[:limit]
