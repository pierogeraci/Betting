"""Rating del rischio di frode sugli eventi sportivi, da serie di quote caricate dall'analista.

Dall'esterno le serie storiche di quote e volumi non si raccolgono: arrivano da un
fornitore o da un'autorità. Segnali, per evento:
- un bookmaker che offre su un esito una quota molto più bassa del consenso degli altri
  (il "bookmaker compiacente" descritto nella relazione);
- un movimento brusco del consenso nelle ultime ore prima dell'inizio;
- un volume anomalo su un esito rispetto agli altri.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

THRESHOLDS = {"scostamento_bookmaker": 0.15, "movimento_finale": 0.12, "quota_volume": 0.7}
LATE_HOURS = 6


def parse_csv(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """Colonne: evento, inizio, bookmaker, momento, esito, quota; facoltative: sport, competizione, volume."""
    text = data.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.count(";") > text.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    need = {"evento", "bookmaker", "momento", "esito", "quota"}
    fields = {f.strip().lower() for f in reader.fieldnames or []}
    if not need <= fields:
        raise ValueError(
            "Colonne richieste: evento, inizio, bookmaker, momento, esito, quota (facoltative: sport, competizione, volume)."
        )
    rows, errors = [], []

    def when(value: str) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    for n, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        try:
            odds = float(row["quota"].replace(",", "."))
            if odds <= 1:
                raise ValueError
            rows.append(
                {
                    "evento": row["evento"][:300],
                    "inizio": when(row.get("inizio", "")),
                    "bookmaker": row["bookmaker"][:120],
                    "momento": when(row["momento"]),
                    "esito": row["esito"][:40],
                    "quota": odds,
                    "volume": float(row["volume"].replace(",", ".")) if row.get("volume") else None,
                    "sport": row.get("sport", "")[:60],
                    "competizione": row.get("competizione", "")[:200],
                }
            )
        except (ValueError, KeyError, TypeError):
            errors.append(f"Riga {n}: valori non leggibili")
    return rows, errors


def rate(quotes: list[dict[str, Any]], start: datetime | None) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    latest: dict[tuple[str, str], tuple[datetime, float]] = {}
    for q in quotes:
        key = (q["bookmaker"], q["esito"])
        if key not in latest or q["momento"] > latest[key][0]:
            latest[key] = (q["momento"], q["quota"])
    by_outcome: dict[str, dict[str, float]] = defaultdict(dict)
    for (book, outcome), (_, odds) in latest.items():
        by_outcome[outcome][book] = odds
    for outcome, books in by_outcome.items():
        if len(books) < 3:
            continue
        for book, odds in books.items():
            consensus = median(v for b, v in books.items() if b != book)
            gap = (consensus - odds) / consensus
            if gap >= THRESHOLDS["scostamento_bookmaker"]:
                signals.append(
                    {
                        "segnale": "scostamento_bookmaker",
                        "peso": 2,
                        "descrizione": f"{book} offre {odds:.2f} su «{outcome}» contro un consenso di {consensus:.2f} ({gap:.0%} più bassa)",
                    }
                )
    if start is not None:
        for outcome in by_outcome:
            series = sorted((q["momento"], q["quota"]) for q in quotes if q["esito"] == outcome)
            before = [o for t, o in series if t <= start - timedelta(hours=LATE_HOURS)]
            late = [o for t, o in series if start - timedelta(hours=LATE_HOURS) < t <= start]
            if before and late:
                change = (median(before) - median(late)) / median(before)
                if abs(change) >= THRESHOLDS["movimento_finale"]:
                    signals.append(
                        {
                            "segnale": "movimento_finale",
                            "peso": 2 if change > 0 else 1,
                            "descrizione": f"La quota di «{outcome}» passa da {median(before):.2f} a {median(late):.2f} nelle ultime {LATE_HOURS} ore",
                        }
                    )
    volumes: dict[str, float] = defaultdict(float)
    for q in quotes:
        if q.get("volume"):
            volumes[q["esito"]] += q["volume"]
    total = sum(volumes.values())
    if total and len(volumes) >= 2:
        outcome, value = max(volumes.items(), key=lambda kv: kv[1])
        share = value / total
        favourite = min(by_outcome, key=lambda o: median(by_outcome[o].values()))
        if share >= THRESHOLDS["quota_volume"] and outcome != favourite:
            signals.append(
                {
                    "segnale": "quota_volume",
                    "peso": 2,
                    "descrizione": f"{share:.0%} del volume su «{outcome}», che non è il favorito",
                }
            )
    computable = {
        "scostamento_bookmaker": any(len(b) >= 3 for b in by_outcome.values()),
        "movimento_finale": start is not None,
        "quota_volume": bool(total) and len(volumes) >= 2,
    }
    score = sum(s["peso"] for s in signals)
    if not signals and not any(computable.values()):
        rating = "non_determinabile"  # nessun segnale calcolabile: non vale "basso"
    else:
        rating = "alto" if score >= 4 else "medio" if score >= 2 else "basso"
    return {
        "rating": rating,
        "punteggio": score,
        "segnali": signals,
        "calcolabili": computable,
        "bookmaker": sorted({q["bookmaker"] for q in quotes}),
        "esiti": sorted(by_outcome),
        "quote": len(quotes),
    }
