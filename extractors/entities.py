"""Estrazione deterministica delle entità con forma fissa.

URL, domini, link Telegram di canali, portafogli crypto, IBAN, partite IVA,
codici promozionali, numeri di concessione e di licenza. Nessun nome di persona.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.domains import InvalidUrl, find_domain, normalize_url


@dataclass(frozen=True)
class Entity:
    kind: str
    value: str
    start: int
    end: int
    certainty: float = 1.0


URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'()\[\]{}]+")
BARE_DOMAIN_RE = re.compile(
    r"(?i)(?<![@\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|bet|casino|games|win|vip|club|top|xyz|cc|me|co|it|eu|online|site|live|pro|app|info|biz|ru|ua|uk|de|es|fr|mt|cw|tv|gg|ag|ws|to|onion))\b"
)
TELEGRAM_RE = re.compile(
    r"(?i)\b(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?:s/)?(\+?[A-Za-z0-9_]{4,64})"
)
BTC_RE = re.compile(r"\b(bc1[ac-hj-np-z02-9]{25,62}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
ETH_RE = re.compile(r"\b(0x[a-fA-F0-9]{40})\b")
TRX_RE = re.compile(r"\b(T[1-9A-HJ-NP-Za-km-z]{33})\b")
LTC_RE = re.compile(r"\b(ltc1[ac-hj-np-z02-9]{25,62}|[LM][a-km-zA-HJ-NP-Z1-9]{26,33})\b")
XMR_RE = re.compile(r"\b(4[0-9AB][1-9A-HJ-NP-Za-km-z]{93})\b")
IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?)\b")
PIVA_RE = re.compile(
    r"(?i)(?:p\.?\s?iva|partita\s+iva|vat(?:\s+(?:no|number))?|c\.f\.)[\s.:n°#]*((?:IT)?\s?\d{11})\b"
)
PROMO_RE = re.compile(
    r"(?i)(?:codice\s+(?:promo(?:zionale)?|bonus)|promo\s?code|bonus\s?code|coupon|referral\s?code|codice)\s*[:\-–]?\s*[\"'«]?([A-Z0-9]{4,20})\b"
)
ADM_CONCESSION_RE = re.compile(
    r"(?i)(?:concessione|concessionario|licenza|gad|aams|adm)[^\d\n]{0,25}(?:n\.?|nr\.?|numero|no\.?|n°)?\s*[:#]?\s*(1[0-9]{4})\b"
)
CURACAO_RE = re.compile(r"(?i)\b(\d{3,5}/JAZ(?:\d{4}-\d{3})?|OGL/\d{4}/\d+/\d+|GLH-OCCHKTW\d+|8048/JAZ)\b")
MGA_RE = re.compile(r"(?i)\b(MGA/(?:B2C|B2B|CRP)/\d+/\d{4})\b")
UKGC_RE = re.compile(r"(?i)(?:gambling commission|ukgc)[^\d]{0,40}(\d{4,6})\b")


def iban_valid(raw: str) -> bool:
    iban = raw.replace(" ", "").upper()
    if not 15 <= len(iban) <= 34:
        return False
    moved = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in moved)
    return int(digits) % 97 == 1


def piva_valid(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)[-11:]
    if len(digits) != 11:
        return False
    total = 0
    for i, ch in enumerate(digits[:10]):
        n = int(ch)
        if i % 2:
            n *= 2
            n = n - 9 if n > 9 else n
        total += n
    return (10 - total % 10) % 10 == int(digits[10])


def _btc_like(value: str) -> bool:
    # Esclude stringhe che sono parole o numeri lunghi: un indirizzo ha lettere e cifre miste.
    return bool(re.search(r"\d", value)) and bool(re.search(r"[a-zA-Z]", value)) and not value.isupper()


def extract(text: str) -> list[Entity]:
    """Entità trovate nel testo, senza duplicati per (tipo, valore)."""
    found: list[Entity] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str, m: re.Match[str], certainty: float = 1.0) -> None:
        key = (kind, value)
        if key not in seen:
            seen.add(key)
            found.append(Entity(kind, value, m.start(), m.end(), certainty))

    url_spans: list[tuple[int, int]] = []
    for m in URL_RE.finditer(text):
        raw = m.group(0).rstrip(".,;:!?)»")
        try:
            url = normalize_url(raw if "://" in raw else "https://" + raw)
        except InvalidUrl:
            continue
        url_spans.append((m.start(), m.end()))
        if url.host in {"t.me", "telegram.me", "telegram.dog"}:
            continue
        add("url", url.url, m)
        add("dominio", url.registrable, m)
    for m in BARE_DOMAIN_RE.finditer(text):
        if any(a <= m.start() < b for a, b in url_spans):
            continue
        host = find_domain(m.group(1))
        if host:
            try:
                add("dominio", normalize_url(host).registrable, m, 0.8)
            except InvalidUrl:
                pass
    for m in TELEGRAM_RE.finditer(text):
        name = m.group(1)
        if name.lower() in {"share", "joinchat", "addstickers", "proxy", "socks", "iv", "c"}:
            continue
        add("canale_telegram", name.lower() if not name.startswith("+") else name, m)
    for kind, regex in (
        ("portafoglio_btc", BTC_RE),
        ("portafoglio_eth", ETH_RE),
        ("portafoglio_trx", TRX_RE),
        ("portafoglio_ltc", LTC_RE),
        ("portafoglio_xmr", XMR_RE),
    ):
        for m in regex.finditer(text):
            value = m.group(1)
            if kind in {"portafoglio_btc", "portafoglio_ltc"} and not _btc_like(value):
                continue
            add(kind, value, m, 0.9)
    for m in IBAN_RE.finditer(text):
        value = m.group(1).replace(" ", "")
        if iban_valid(value):
            add("iban", value, m)
    for m in PIVA_RE.finditer(text):
        value = re.sub(r"\D", "", m.group(1))
        if piva_valid(value):
            add("partita_iva", value, m)
    for m in PROMO_RE.finditer(text):
        value = m.group(1)
        if re.search(r"[A-Z]", value) and not value.isdigit():
            add("codice_promo", value.upper(), m, 0.7)
    for m in ADM_CONCESSION_RE.finditer(text):
        add("concessione_adm", m.group(1), m, 0.8)
    for kind, regex in (("licenza_curacao", CURACAO_RE), ("licenza_mga", MGA_RE), ("licenza_ukgc", UKGC_RE)):
        for m in regex.finditer(text):
            add(kind, m.group(1).upper(), m, 0.9)
    return found
