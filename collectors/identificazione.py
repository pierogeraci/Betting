"""Area identificazione: registrazione, documento, più account per conto."""

from __future__ import annotations

import re

from collectors import terms
from collectors.base import ASSENTE, ND, PRESENTE, Indicator, Page, evidence, find_terms, normalize

NOME = "identificazione"
VERSIONE = "1"
AREA = "Identificazione"


def _ind(code: str, value: str, certainty: float, ev: dict | None = None) -> Indicator:
    return Indicator(code, value, certainty, NOME, VERSIONE, ev or {}, AREA)


def _first(pages: list[Page], words: list[str]):
    for p in pages:
        if p.readable:
            found = find_terms(p, words)
            if found:
                return p, found[1]
    return None


def _registration_link(pages: list[Page]):
    pattern = re.compile("|".join(re.escape(normalize(t)) for t in terms.REGISTRATION_REQUIRED))
    for p in pages:
        if p.status != "riuscito":
            continue
        for href, label in p.links:
            if pattern.search(normalize(label)) or re.search(r"(?i)sign-?up|register|registra", href):
                return p, f"Link «{label or href}» → {href}"
        for form in p.parsed.forms:
            names = " ".join(n for _, n in form["inputs"]).lower()
            if "password" in names and any(k in names for k in ("email", "user", "phone", "telefono")):
                return p, f"Modulo di registrazione con campi: {names[:120]}"
    return None


def collect(pages: list[Page]) -> list[Indicator]:
    out: list[Indicator] = []
    no_reg = _first(pages, terms.NO_REGISTRATION)
    if no_reg:
        out.append(_ind("assenza_registrazione", PRESENTE, 0.8, evidence(*no_reg)))
    else:
        reg = _registration_link(pages)
        if reg:
            out.append(_ind("assenza_registrazione", ASSENTE, 0.6, evidence(*reg)))
        else:
            out.append(
                _ind(
                    "assenza_registrazione", ND, 0.0, {"motivo": "Nessun percorso di registrazione osservato"}
                )
            )

    no_doc = _first(pages, terms.NO_DOCUMENT)
    if no_doc:
        out.append(_ind("assenza_documento", PRESENTE, 0.75, evidence(*no_doc)))
    else:
        doc = _first(pages, terms.DOCUMENT_REQUIRED)
        if doc:
            out.append(_ind("assenza_documento", ASSENTE, 0.6, evidence(*doc)))
        else:
            out.append(
                _ind("assenza_documento", ND, 0.0, {"motivo": "Condizioni sull'identificazione non lette"})
            )

    multi = _first(pages, terms.MULTIPLE_ACCOUNTS_ALLOWED)
    if multi:
        out.append(_ind("piu_account_per_conto", PRESENTE, 0.7, evidence(*multi)))
    else:
        single = _first(pages, terms.ONE_ACCOUNT_ONLY)
        if single:
            out.append(_ind("piu_account_per_conto", ASSENTE, 0.7, evidence(*single)))
        else:
            out.append(
                _ind(
                    "piu_account_per_conto",
                    ND,
                    0.0,
                    {"motivo": "Condizioni d'uso non lette o senza clausola sugli account"},
                )
            )
    return out
