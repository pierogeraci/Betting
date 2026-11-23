"""Area offerta: tipi di gioco e loro classificazione, quote visibili, servizi esterni
(chat dal vivo, immagini), link di pagamento rapido, lingua e valuta.

I link di pagamento rapido si osservano e basta: non si seguono né si compilano.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from collectors import terms
from collectors.base import ASSENTE, ND, PRESENTE, Indicator, Page, evidence, normalize, readable_home
from core.domains import registrable_domain

NOME = "offerta"
VERSIONE = "1"
AREA = "Offerta"
ODDS_RE = re.compile(r"(?<![\d.,])(?:[1-9]\d?)[.,]\d{2}(?![\d.,%])")
CONFIG = Path(__file__).resolve().parent.parent / "config" / "giochi.yaml"


@lru_cache
def game_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _ind(code: str, value: str, certainty: float, ev: dict | None = None) -> Indicator:
    return Indicator(code, value, certainty, NOME, VERSIONE, ev or {}, AREA)


def game_types(pages: list[Page]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for p in pages:
        if not p.readable:
            continue
        text = p.text_norm
        for code, spec in game_config()["tipi"].items():
            if code in found:
                continue
            for term in spec["termini"]:
                m = re.search(r"(?<![a-z0-9])" + re.escape(normalize(term)) + r"(?![a-z0-9])", text)
                if m:
                    found[code] = {
                        "nome": spec["nome"],
                        "termine": term,
                        "criteri": spec["criteri"],
                        "url": p.url,
                        "snapshot_id": p.snapshot_id,
                        "estratto": text[max(0, m.start() - 60) : m.end() + 60],
                    }
                    break
    return found


def _site_base(pages: list[Page]) -> str:
    return registrable_domain(pages[0].host) if pages and pages[0].host else ""


def collect(pages: list[Page]) -> list[Indicator]:
    readable = [p for p in pages if p.readable]
    if not readable:
        codes = [
            "tipi_gioco",
            "quote_visibili",
            "chat_dal_vivo",
            "immagini_esterne",
            "link_pagamento_rapido",
            "lingua_italiana",
        ]
        return [_ind(c, ND, 0.0, {"motivo": "Nessuna pagina leggibile"}) for c in codes]
    out: list[Indicator] = []
    home = readable_home(pages)
    games = game_types(readable)
    if games:
        first = next(iter(games.values()))
        out.append(
            _ind(
                "tipi_gioco",
                PRESENTE,
                0.8,
                {
                    "url": first["url"],
                    "snapshot_id": first["snapshot_id"],
                    "estratto": first["estratto"],
                    "tipi": games,
                },
            )
        )
    elif home:
        out.append(
            _ind(
                "tipi_gioco",
                ASSENTE,
                0.5,
                evidence(home, "Nessun tipo di gioco riconosciuto nella pagina principale"),
            )
        )
    else:
        out.append(_ind("tipi_gioco", ND, 0.0, {"motivo": "Pagina principale non letta"}))

    odds_page, odds = None, []
    for p in readable:
        values = ODDS_RE.findall(p.text)
        if len(values) >= 12:
            odds_page, odds = p, values
            break
    if odds_page:
        out.append(
            _ind(
                "quote_visibili",
                PRESENTE,
                0.6,
                evidence(odds_page, " ".join(odds[:20]), numero_quote=len(odds)),
            )
        )
    else:
        out.append(
            _ind("quote_visibili", ND, 0.0, {"motivo": "Nessun palinsesto con quote nelle pagine lette"})
        )

    base = _site_base(pages)
    chats = {
        name
        for p in pages
        for h in p.all_hosts
        for dom, name in terms.LIVE_CHAT_HOSTS.items()
        if h == dom or h.endswith("." + dom)
    }
    if chats:
        out.append(
            _ind(
                "chat_dal_vivo",
                PRESENTE,
                0.9,
                evidence(
                    readable[0],
                    "Servizi di chat caricati dalla pagina: " + ", ".join(sorted(chats)),
                    servizi=sorted(chats),
                ),
            )
        )
    else:
        out.append(
            _ind("chat_dal_vivo", ND, 0.0, {"motivo": "Nessun servizio di chat noto tra le risorse caricate"})
        )

    images = set()
    any_image = False
    for p in pages:
        for src, _ in p.parsed.images:
            any_image = any_image or bool(src)
            host = (urlsplit(p.absolute(src)).hostname or "").lower()
            if host and registrable_domain(host) != base:
                label = next(
                    (n for d, n in terms.IMAGE_HOSTS.items() if host == d or host.endswith("." + d)), host
                )
                images.add(label)
    if images:
        out.append(
            _ind(
                "immagini_esterne",
                PRESENTE,
                0.8,
                evidence(
                    readable[0],
                    "Immagini servite da: " + ", ".join(sorted(images)[:10]),
                    servizi=sorted(images),
                ),
            )
        )
    elif home and any_image:
        out.append(
            _ind(
                "immagini_esterne",
                ASSENTE,
                0.5,
                evidence(home, "Tutte le immagini sono servite dal dominio del sito"),
            )
        )
    else:
        out.append(_ind("immagini_esterne", ND, 0.0, {"motivo": "Nessuna immagine nelle pagine lette"}))

    rapid = []
    for p in pages:
        for href, label in p.links:
            host = (urlsplit(href).hostname or "").lower()
            if not host or registrable_domain(host) == base:
                continue
            if any(t in normalize(label) for t in terms.PAYMENT_LINK_TERMS):
                rapid.append({"testo": label[:80], "link": href[:300], "dominio": registrable_domain(host)})
    if rapid:
        out.append(
            _ind(
                "link_pagamento_rapido",
                PRESENTE,
                0.6,
                evidence(readable[0], f"«{rapid[0]['testo']}» → {rapid[0]['link']}", link=rapid[:10]),
            )
        )
    else:
        out.append(
            _ind(
                "link_pagamento_rapido", ND, 0.0, {"motivo": "Nessun link di pagamento verso domini esterni"}
            )
        )

    italian = None
    for p in readable:
        lang = re.search(r'(?i)<html[^>]*\blang=["\']?([a-z-]+)', p.html or "")
        if lang and lang.group(1).lower().startswith("it"):
            italian = (p, f'Attributo lang="{lang.group(1)}"')
            break
        if (
            len(
                re.findall(
                    r"(?i)\b(scommesse|gioca|vinci|registrati|deposito|quote|bonus di benvenuto)\b", p.text
                )
            )
            >= 3
        ):
            italian = (p, "Testo in italiano")
            break
    if italian:
        out.append(_ind("lingua_italiana", PRESENTE, 0.8, evidence(*italian)))
    elif home:
        out.append(_ind("lingua_italiana", ASSENTE, 0.6, evidence(home, "Pagina principale non in italiano")))
    else:
        out.append(_ind("lingua_italiana", ND, 0.0, {"motivo": "Pagina principale non letta"}))
    return out
