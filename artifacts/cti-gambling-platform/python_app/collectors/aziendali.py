"""Area dati aziendali: ragione sociale, partita IVA o numero di registrazione, sede."""

from __future__ import annotations

import re

from collectors.base import ASSENTE, ND, PRESENTE, Indicator, Page, evidence
from extractors.entities import extract

NOME = "dati_aziendali"
VERSIONE = "1"
AREA = "Dati aziendali"

COMPANY_RE = re.compile(
    r"\b((?:[A-Z0-9][\w&.'-]*\s){0,5}[A-Z0-9][\w&.'-]*,?\s(?:S\.?p\.?A\.?|S\.?r\.?l\.?s?|Ltd\.?|Limited|N\.?V\.?|B\.?V\.?|GmbH|LLC|S\.?A\.?|Inc\.?|OÜ|SIA|Plc|S\.?L\.?|Corp\.?))(?=[\s,.;)]|$)"
)
REGNO_RE = re.compile(
    r"(?i)(?:company|registration|reg\.?|registro|commercial register|kvk|c\.r\.)\s*(?:no\.?|number|n\.?|nr\.?)?\s*[:#]?\s*([A-Z]{0,3}\s?\d[\d\s/-]{3,14}\d)"
)
ADDRESS_RE = re.compile(
    r"(?i)((?:registered (?:office|address)|sede legale|sede|address|indirizzo)\s*[:\-]?\s*[^.\n]{8,140}?(?:curacao|curaçao|malta|cyprus|cipro|italia|italy|gibraltar|london|united kingdom|estonia|costa rica|seychelles|anjouan|comoros|belize|panama|netherlands|ireland|isle of man|\b\d{5}\b))"
)


def _ind(code: str, value: str, certainty: float, ev: dict | None = None) -> Indicator:
    return Indicator(code, value, certainty, NOME, VERSIONE, ev or {}, AREA)


def _search(pages: list[Page], regex: re.Pattern[str]):
    # Prima il piè di pagina, dove i dati societari stanno di solito, poi tutto il testo.
    for p in pages:
        for source in (p.footer_text, p.text):
            m = regex.search(source)
            if m:
                return p, source[max(0, m.start() - 40) : m.end() + 40], m.group(1).strip()
    return None


def collect(pages: list[Page]) -> list[Indicator]:
    readable = [p for p in pages if p.readable]
    out: list[Indicator] = []
    if not readable:
        return [
            _ind(c, ND, 0.0, {"motivo": "Nessuna pagina leggibile"})
            for c in ("ragione_sociale_dichiarata", "partita_iva_dichiarata", "sede_dichiarata")
        ]
    # "Assente" solo se è stata letta la home (con il piè di pagina) o una pagina "chi siamo".
    absent_ok = any(p.footer_text for p in readable)
    hit = _search(readable, COMPANY_RE)
    if hit:
        out.append(
            _ind("ragione_sociale_dichiarata", PRESENTE, 0.75, evidence(hit[0], hit[1], valore=hit[2]))
        )
    else:
        out.append(
            _ind(
                "ragione_sociale_dichiarata",
                ASSENTE if absent_ok else ND,
                0.5 if absent_ok else 0.0,
                evidence(readable[0], "Nessuna ragione sociale nel piè di pagina letto")
                if absent_ok
                else {"motivo": "Piè di pagina non letto"},
            )
        )
    piva = next(((p, e) for p in readable for e in extract(p.text) if e.kind == "partita_iva"), None)
    if piva:
        out.append(
            _ind(
                "partita_iva_dichiarata",
                PRESENTE,
                0.9,
                evidence(
                    piva[0], piva[0].text[max(0, piva[1].start - 30) : piva[1].end + 10], valore=piva[1].value
                ),
            )
        )
    else:
        reg = _search(readable, REGNO_RE)
        if reg:
            out.append(
                _ind(
                    "partita_iva_dichiarata",
                    PRESENTE,
                    0.6,
                    evidence(reg[0], reg[1], valore=reg[2], tipo="numero di registrazione estero"),
                )
            )
        else:
            out.append(
                _ind(
                    "partita_iva_dichiarata",
                    ASSENTE if absent_ok else ND,
                    0.5 if absent_ok else 0.0,
                    evidence(readable[0], "Nessuna partita IVA o numero di registrazione")
                    if absent_ok
                    else {"motivo": "Piè di pagina non letto"},
                )
            )
    addr = _search(readable, ADDRESS_RE)
    if addr:
        out.append(_ind("sede_dichiarata", PRESENTE, 0.6, evidence(addr[0], addr[1], valore=addr[2][:200])))
    else:
        out.append(_ind("sede_dichiarata", ND, 0.0, {"motivo": "Sede non trovata nel testo letto"}))
    return out
