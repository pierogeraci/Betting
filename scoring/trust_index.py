"""Calcolo di vulnerabilità, minaccia e Trust Index secondo la matrice v0.5.

Funzioni pure: ricevono indicatori e puntate, restituiscono il risultato con tutti
i passaggi intermedi, così che il portale possa mostrarli come i quattro fogli.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from scoring.config import level, load_rules


@dataclass
class Bet:
    """Una puntata osservata: importo puntato, importo vinto, valuta, momento."""

    stake: float
    won: float
    currency: str = "EUR"
    at: datetime | None = None
    game: str | None = None


@dataclass
class VulnItem:
    code: str
    name: str
    weight: float
    value: str  # presente | assente | non_determinabile
    evidence: dict[str, Any] = field(default_factory=dict)
    certainty: float = 0.0


@dataclass
class Vulnerability:
    items: list[VulnItem]
    score: float  # somma dei pesi delle voci presenti
    score_max: float  # se tutte le non determinabili fossero presenti
    coverage: float
    level: str | None
    level_max: str | None


@dataclass
class Threat:
    bets_total: int
    bets_used: int
    excluded_currency: int
    window_start: datetime | None
    window_end: datetime | None
    refined: dict[str, float] | None  # i cinque valori del foglio "Raffinamento Dati"
    variables: list[dict[str, Any]]
    score: float | None
    level: str | None
    reason: str | None = None


@dataclass
class TrustIndex:
    version: str
    scope: str
    vulnerability: Vulnerability
    threat: Threat
    value: float | None
    risk_class: str | None
    excluded_reason: str | None = None
    flags: list[str] = field(default_factory=list)

    def detail(self) -> dict[str, Any]:
        def items() -> list[dict[str, Any]]:
            return [
                {
                    "codice": i.code,
                    "nome": i.name,
                    "peso": i.weight,
                    "valore": i.value,
                    "certezza": i.certainty,
                    "evidenza": i.evidence,
                }
                for i in self.vulnerability.items
            ]

        t = self.threat
        return {
            "versione": self.version,
            "ambito": self.scope,
            "vulnerabilita": {
                "voci": items(),
                "punteggio": self.vulnerability.score,
                "punteggio_massimo": self.vulnerability.score_max,
                "copertura": self.vulnerability.coverage,
                "livello": self.vulnerability.level,
                "livello_massimo": self.vulnerability.level_max,
            },
            "minaccia": {
                "puntate_totali": t.bets_total,
                "puntate_usate": t.bets_used,
                "escluse_valuta": t.excluded_currency,
                "finestra_inizio": t.window_start.isoformat() if t.window_start else None,
                "finestra_fine": t.window_end.isoformat() if t.window_end else None,
                "raffinamento": t.refined,
                "variabili": t.variables,
                "punteggio": t.score,
                "livello": t.level,
                "motivo": t.reason,
            },
            "trust_index": self.value,
            "classe": self.risk_class,
            "esclusione": self.excluded_reason,
            "segnalazioni": self.flags,
        }


def vulnerability(
    indicators: dict[str, dict[str, Any]], rules: dict[str, Any] | None = None
) -> Vulnerability:
    """`indicators`: codice → {valore, evidenza, certezza}. Le voci mancanti sono non determinabili."""
    rules = rules or load_rules()
    cfg = rules["vulnerabilita"]
    items: list[VulnItem] = []
    for code, spec in cfg["voci"].items():
        found = indicators.get(code) or {}
        items.append(
            VulnItem(
                code=code,
                name=spec["nome"],
                weight=float(spec["peso"]),
                value=found.get("valore", "non_determinabile"),
                evidence=found.get("evidenza") or {},
                certainty=float(found.get("certezza") or 0),
            )
        )
    determined = [i for i in items if i.value != "non_determinabile"]
    score = sum(i.weight for i in items if i.value == "presente")
    score_max = score + sum(i.weight for i in items if i.value == "non_determinabile")
    coverage = len(determined) / len(items) if items else 0.0
    lvl = level(score, cfg["livelli"])
    lvl_max = level(score_max, cfg["livelli"])
    # Con voci non determinabili il livello è certo solo se il minimo e il massimo coincidono.
    if coverage < cfg["copertura_minima"] and lvl != lvl_max:
        shown = None
    else:
        shown = lvl
    return Vulnerability(items, score, score_max, round(coverage, 3), shown, lvl_max)


def _vote(value: float, thresholds: list[float]) -> int:
    low, high = thresholds
    if value < low:
        return 1
    if value < high:
        return 2
    return 3


VOTE_NAMES = {1: "basso", 2: "medio", 3: "alto"}


def threat(bets: list[Bet], rules: dict[str, Any] | None = None) -> Threat:
    rules = rules or load_rules()
    cfg = rules["minaccia"]
    rates = {k.upper(): float(v) for k, v in (rules.get("tassi_eur") or {}).items()}
    converted: list[tuple[float, float, datetime | None]] = []
    excluded = 0
    for bet in bets:
        rate = rates.get((bet.currency or "EUR").upper())
        if rate is None:
            excluded += 1
            continue
        converted.append((bet.stake * rate, bet.won * rate, bet.at))
    window_start = window_end = None
    dated = [c for c in converted if c[2] is not None]
    if dated:
        window_end = max(c[2] for c in dated)
        window_start = window_end - timedelta(hours=cfg["finestra_ore"])
        converted = [c for c in converted if c[2] is None or c[2] > window_start]
    base = Threat(len(bets), len(converted), excluded, window_start, window_end, None, [], None, None)
    # Come nel foglio: una puntata conta se l'importo è maggiore di zero; vittoria se vinto > 0.
    placed = [c for c in converted if c[0] > 0]
    if len(placed) < cfg["puntate_minime"]:
        base.reason = (
            f"Servono almeno {cfg['puntate_minime']} puntate nella finestra di {cfg['finestra_ore']} ore: "
            f"ne ho {len(placed)}."
        )
        return base
    count = len(placed)
    total_staked = sum(c[0] for c in converted)
    wins = sum(1 for c in converted if c[1] > 0)
    total_won = sum(c[1] for c in converted)
    refined = {
        "numero_puntate": count,
        "totale_scommesso": round(total_staked, 2),
        "numero_vittorie": wins,
        "totale_vinto": round(total_won, 2),
        "percentuale_vincite": round(wins / count, 4),
    }
    values = {
        "profilo_rischio": math.ceil(total_staked / count),
        "rendimento_lordo": total_won,
        "percentuale_vincite": wins / count,
    }
    variables = []
    for code, spec in cfg["variabili"].items():
        vote = _vote(values[code], spec["soglie"])
        variables.append(
            {
                "codice": code,
                "nome": spec["nome"],
                "formula": spec["formula"],
                "soglie": spec["soglie"],
                "valore": round(values[code], 4),
                "voto": vote,
                "livello": VOTE_NAMES[vote],
            }
        )
    score = math.ceil(sum(v["voto"] for v in variables) / len(variables)) * cfg["moltiplicatore"]
    base.refined = refined
    base.variables = variables
    base.score = float(score)
    base.level = level(score, cfg["livelli"])
    return base


def compute(
    indicators: dict[str, dict[str, Any]],
    bets: list[Bet],
    *,
    adm_outcome: str = "non_determinabile",
    adm_without_title: bool = False,
    scope: str = "piattaforma",
    rules: dict[str, Any] | None = None,
) -> TrustIndex:
    rules = rules or load_rules()
    vuln = vulnerability(indicators, rules)
    thr = threat(bets, rules)
    result = TrustIndex(rules["version"], scope, vuln, thr, None, None)
    if adm_without_title and rules["regole"].get("segnala_adm_senza_titolo"):
        result.flags.append("adm_senza_titolo")
    if adm_outcome == "concessionario" and rules["regole"].get("escludi_concessionari"):
        result.excluded_reason = "Concessionario ADM: escluso dalla valutazione di illegalità."
        return result
    if vuln.level is None:
        result.excluded_reason = (
            f"Copertura delle vulnerabilità {vuln.coverage:.0%} sotto la soglia: il sito va all'analista."
        )
        return result
    if thr.score is None:
        result.excluded_reason = (
            "Minaccia non determinabile: mancano i dati di puntata. Si mostra la sola vulnerabilità."
        )
        return result
    value = float(Decimal(str(vuln.score + thr.score)) / Decimal(str(rules["trust_index"]["divisore"])))
    result.value = value
    result.risk_class = level(value, rules["trust_index"]["livelli"])
    return result
