"""Parole chiave: prefiltro delle sonde e avvisi all'analista."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from collectors.base import normalize
from core.models import ParolaChiave


@dataclass(frozen=True)
class Keyword:
    term: str
    category: str
    alert: bool


def active_keywords(session: Session) -> list[Keyword]:
    rows = session.execute(
        select(ParolaChiave).where(ParolaChiave.attiva.is_(True)).order_by(ParolaChiave.termine)
    ).scalars()
    return [Keyword(r.termine, r.categoria, r.avviso) for r in rows]


def matches(text: str, keywords: list[Keyword]) -> list[Keyword]:
    """Parole chiave presenti nel testo, dopo la normalizzazione (accenti, emoji, sosia)."""
    from extractors.normalize import normalize_text

    norm = normalize(normalize_text(text))
    found = []
    for kw in keywords:
        term = normalize(kw.term)
        if term and re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", norm):
            found.append(kw)
    return found
