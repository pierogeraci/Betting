"""Area titolo a operare: logo e numero di concessione ADM esposti, licenze estere dichiarate.

Il collettore registra cosa il sito dichiara. Se il sito è autorizzato lo decide solo
il confronto con gli elenchi ADM (core/adm.py).
"""

from __future__ import annotations

import re

from collectors.base import ASSENTE, ND, PRESENTE, Indicator, Page, evidence, normalize
from extractors.entities import extract

NOME = "titolo_operare"
VERSIONE = "1"
AREA = "Titolo a operare"

ADM_LOGO = re.compile(
    r"(?i)(?:^|[/_\-.\s])(adm|aams)(?:[/_\-.\s]|$)|agenzia (?:delle )?dogane|logo[-_]?adm|gioco[-_]?legale|contrassegno"
)
FOREIGN = {
    "Curaçao": r"curacao|curaçao|antillephone|gaming control board|cgcb|cgaweb|8048/jaz",
    "Malta (MGA)": r"malta gaming authority|\bmga\b|mga/b2c",
    "Regno Unito (UKGC)": r"uk gambling commission|gambling commission",
    "Gibilterra": r"gibraltar (?:gambling|regulatory|licensing)",
    "Kahnawake": r"kahnawake",
    "Anjouan": r"anjouan",
    "Costa Rica": r"costa rica",
    "Isola di Man": r"isle of man gambling|gambling supervision commission",
    "Cipro": r"national betting authority|cyprus",
    "Estonia": r"estonian tax and customs|emta",
    "Tobique": r"tobique",
}


def _ind(code: str, value: str, certainty: float, ev: dict | None = None) -> Indicator:
    return Indicator(code, value, certainty, NOME, VERSIONE, ev or {}, AREA)


def collect(pages: list[Page]) -> list[Indicator]:
    out: list[Indicator] = []
    readable = [p for p in pages if p.readable]
    logo = None
    for p in pages:
        if p.status != "riuscito":
            continue
        for src, alt in p.parsed.images:
            if ADM_LOGO.search(src.rsplit("/", 1)[-1]) or ADM_LOGO.search(alt):
                logo = (p, f"Immagine {src.rsplit('/', 1)[-1] or src} «{alt.strip()}»")
                break
        if logo:
            break
    if logo:
        out.append(_ind("logo_adm_esposto", PRESENTE, 0.7, evidence(*logo)))
    elif readable:
        out.append(
            _ind(
                "logo_adm_esposto",
                ASSENTE,
                0.5,
                evidence(readable[0], "Nessuna immagine con il marchio ADM/AAMS"),
            )
        )
    else:
        out.append(_ind("logo_adm_esposto", ND, 0.0, {"motivo": "Nessuna pagina leggibile"}))

    number = None
    for p in readable:
        for e in extract(p.text):
            if e.kind == "concessione_adm":
                number = (p, p.text[max(0, e.start - 60) : e.end + 40], e.value)
                break
        if number:
            break
    if number:
        out.append(
            _ind(
                "numero_concessione_dichiarato",
                PRESENTE,
                0.8,
                evidence(number[0], number[1], numero=number[2]),
            )
        )
    elif readable:
        out.append(
            _ind(
                "numero_concessione_dichiarato",
                ASSENTE,
                0.5,
                evidence(readable[0], "Nessun numero di concessione nel testo letto"),
            )
        )
    else:
        out.append(_ind("numero_concessione_dichiarato", ND, 0.0, {"motivo": "Nessuna pagina leggibile"}))

    licences: dict[str, str] = {}
    first_page = None
    for p in readable:
        text = normalize(p.text)
        for name, pattern in FOREIGN.items():
            m = re.search(pattern, text)
            if m and name not in licences:
                licences[name] = text[max(0, m.start() - 70) : m.end() + 70]
                first_page = first_page or p
        for e in extract(p.text):
            if e.kind.startswith("licenza_"):
                licences.setdefault(e.kind.replace("licenza_", "").upper(), e.value)
                first_page = first_page or p
    if licences:
        name = next(iter(licences))
        out.append(
            _ind(
                "licenza_estera_dichiarata",
                PRESENTE,
                0.7,
                evidence(first_page, licences[name], licenze=sorted(licences)),
            )
        )
    elif readable:
        out.append(
            _ind(
                "licenza_estera_dichiarata",
                ASSENTE,
                0.4,
                evidence(readable[0], "Nessuna licenza estera citata nel testo letto"),
            )
        )
    else:
        out.append(_ind("licenza_estera_dichiarata", ND, 0.0, {"motivo": "Nessuna pagina leggibile"}))
    return out
