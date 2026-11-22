"""Valutazione sul set etichettato: precisione e richiamo di entità e classificatore.

Uso: python -m core.evaluation [--ambito entita|classificatore|gold]

- entita, classificatore: sulle etichette dell'analista nel database;
- gold: sugli esempi sintetici di tests/gold, senza database (verifica della pipeline).

Ogni esecuzione aggiunge una riga a docs/valutazioni.md.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime
from pathlib import Path

from extractors.classifier import Classifier, Example, metrics
from extractors.entities import extract
from extractors.normalize import normalize_text

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "tests" / "gold" / "esempi.jsonl"
LOG = ROOT / "docs" / "valutazioni.md"
HEADER = "| Data (UTC) | Ambito | Esempi | Precisione | Richiamo | F1 | Note |\n| --- | --- | --- | --- | --- | --- | --- |\n"


def log_line(scope: str, n: int, m: dict, note: str = "") -> None:
    LOG.parent.mkdir(exist_ok=True)
    if not LOG.exists():
        LOG.write_text(
            "# Valutazioni\n\nUna riga per esecuzione di `make eval`. I numeri si riportano come escono.\n\n"
            + HEADER,
            encoding="utf-8",
        )
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            f"| {datetime.now(UTC):%Y-%m-%d %H:%M} | {scope} | {n} | {m.get('precisione', '')} | {m.get('richiamo', '')} | {m.get('f1', '')} | {note} |\n"
        )


def entity_scores(items: list[tuple[str, list[dict]]]) -> tuple[dict, list[dict]]:
    expected_total = found_total = correct = 0
    errors = []
    for text, expected_list in items:
        expected = {(e["tipo"], e["valore"].lower()) for e in expected_list}
        kinds = (
            {k for k, _ in expected}
            | {"url", "dominio", "canale_telegram", "codice_promo", "iban"}
            | {k for k, _ in expected}
        )
        found = {
            (e.kind, e.value.lower())
            for e in extract(normalize_text(text))
            if e.kind in kinds or e.kind.startswith("portafoglio_")
        }
        expected_total += len(expected)
        found_total += len(found)
        correct += len(expected & found)
        errors += [
            {"testo": text[:80], "atteso": f"{k}: {v}", "ottenuto": "mancante"}
            for k, v in sorted(expected - found)
        ]
        errors += [
            {"testo": text[:80], "atteso": "nessuno", "ottenuto": f"{k}: {v}"}
            for k, v in sorted(found - expected)
        ]
    p = correct / found_total if found_total else 0.0
    r = correct / expected_total if expected_total else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {
        "precisione": round(p, 3),
        "richiamo": round(r, 3),
        "f1": round(f1, 3),
        "attese": expected_total,
        "trovate": found_total,
    }, errors


def cross_validate(examples: list[Example], folds: int = 5, seed: int = 0) -> tuple[dict, list[dict]]:
    """Validazione incrociata: addestramento solo su esempi non Telegram, test anche su Telegram."""
    allowed = [e for e in examples if e.source.split(":")[0] != "telegram"]
    telegram = [e for e in examples if e.source.split(":")[0] == "telegram"]
    rng = random.Random(seed)  # noqa: S311 - suddivisione ripetibile, non crittografia
    rng.shuffle(allowed)
    truth, predicted, errors = [], [], []
    for k in range(folds):
        test = allowed[k::folds]
        train = [e for i, e in enumerate(allowed) if i % folds != k]
        model = Classifier("tfidf").train(train)
        probs = model.predict_proba([e.text for e in test])
        for e, p in zip(test, probs, strict=True):
            truth.append(e.label)
            predicted.append(p >= 0.5)
            if e.label != (p >= 0.5):
                errors.append({"testo": e.text[:80], "atteso": e.label, "ottenuto": round(p, 2)})
    if telegram:
        model = Classifier("tfidf").train(allowed)
        for e, p in zip(telegram, model.predict_proba([e.text for e in telegram]), strict=True):
            truth.append(e.label)
            predicted.append(p >= 0.5)
    return metrics(truth, predicted), errors


def gold() -> None:
    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    ent, ent_errors = entity_scores([(r["testo"], r["entita"]) for r in rows])
    cls, cls_errors = cross_validate([Example(r["testo"], r["pubblicita_gioco"], r["fonte"]) for r in rows])
    print(f"Esempi sintetici: {len(rows)}")
    print(f"Entità       precisione {ent['precisione']}  richiamo {ent['richiamo']}  F1 {ent['f1']}")
    print(f"Classificatore precisione {cls['precisione']}  richiamo {cls['richiamo']}  F1 {cls['f1']}")
    for err in (ent_errors + cls_errors)[:10]:
        print("  errore:", err)
    log_line("gold-entita", len(rows), ent, "esempi sintetici")
    log_line("gold-classificatore", len(rows), cls, "esempi sintetici, validazione incrociata a 5")


def database(scope: str) -> None:
    from core.analysis import evaluate_entities, train_classifier
    from core.db import session_scope

    with session_scope() as session:
        if scope in {"entita", "tutto"}:
            m = evaluate_entities(session)
            print("Entità:", m)
            log_line("entita", m["attese"], m | {"f1": ""}, "etichette dell'analista")
        if scope in {"classificatore", "tutto"}:
            m = train_classifier(session)
            print("Classificatore:", m)
            if "errore" not in m:
                log_line(
                    "classificatore",
                    m.get("veri_positivi", 0) + m.get("falsi_negativi", 0),
                    m,
                    m.get("versione", ""),
                )


def main() -> None:
    parser = argparse.ArgumentParser(prog="core.evaluation")
    parser.add_argument("--ambito", default="tutto", choices=["tutto", "entita", "classificatore", "gold"])
    args = parser.parse_args()
    gold() if args.ambito == "gold" else database(args.ambito)


if __name__ == "__main__":
    main()
