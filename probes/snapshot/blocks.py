"""Riconosce le pagine di blocco: captcha, verifiche anti-bot, blocchi geografici.

Serve solo a riconoscerle. Una pagina bloccata va in revisione manuale: non si
tenta alcun aggiramento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Marcatori di pagine di verifica: se presenti, la pagina è una barriera.
_CHALLENGE = [
    (r"(?i)<title>\s*just a moment", "verifica_antibot"),
    (r"(?i)cdn-cgi/challenge-platform|cf-chl-|__cf_chl", "verifica_antibot"),
    (r"(?i)attention required!\s*\|\s*cloudflare", "verifica_antibot"),
    (r"(?i)checking (if the site connection is secure|your browser before)", "verifica_antibot"),
    (r"(?i)captcha-delivery\.com|datadome", "verifica_antibot"),
    (r"(?i)pardon our interruption|incapsula incident|_incapsula_resource", "verifica_antibot"),
    (r"(?i)px-captcha|perimeterx", "verifica_antibot"),
    (r"(?i)<title>\s*access denied", "accesso_negato"),
]
# Widget captcha: contano come blocco solo se la pagina non ha altro contenuto.
_WIDGET = r"(?i)g-recaptcha|recaptcha/api\.js|h-captcha|hcaptcha\.com|cf-turnstile|geetest|captcha"
_GEO = (
    r"(?i)not available in your (country|region|location)|restricted (country|territory|jurisdiction)"
    r"|non (è|e') disponibile nel tuo paese|your country is (blocked|restricted)|geo.?block"
)
_STATUS = {
    401: "accesso_negato",
    403: "accesso_negato",
    407: "accesso_negato",
    429: "limite_richieste",
    451: "blocco_legale",
    503: "servizio_non_disponibile",
}


@dataclass(frozen=True)
class Verdict:
    blocked: bool
    reason: str | None = None
    excerpt: str | None = None


def visible_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(text.split())


def _excerpt(html: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 60)
    return " ".join(html[start : match.end() + 60].split())[:300]


def detect_block(status: int | None, html: str) -> Verdict:
    """Decide se la pagina ottenuta è una barriera e non il contenuto del sito."""
    html = html or ""
    for pattern, reason in _CHALLENGE:
        match = re.search(pattern, html)
        if match:
            return Verdict(True, reason, _excerpt(html, match))
    text = visible_text(html)
    geo = re.search(_GEO, text)
    if geo and (len(text) < 3000 or status in {403, 451}):
        return Verdict(True, "blocco_geografico", _excerpt(text, geo))
    if status in _STATUS:
        reason = _STATUS[status]
        if status == 503 and len(text) > 3000:
            # Un 503 con una pagina piena di contenuto è un errore del sito, non una barriera.
            return Verdict(False)
        return Verdict(True, reason, text[:300] or f"HTTP {status}")
    widget = re.search(_WIDGET, html)
    if widget and len(text) < 600:
        return Verdict(True, "captcha", _excerpt(html, widget))
    return Verdict(False)
