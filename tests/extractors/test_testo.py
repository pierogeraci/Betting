import json
from pathlib import Path

import pytest

from extractors.classifier import Classifier, Example, TrainingDataError, usable_for_training
from extractors.entities import extract, iban_valid, piva_valid
from extractors.normalize import normalize_text
from extractors.text import analyse, language, sentiment, summary

GOLD = Path(__file__).resolve().parent.parent / "gold" / "esempi.jsonl"


def test_normalize_deobfuscates():
    assert normalize_text("s.c.o.m.m.e.s.s.e") == "scommesse"
    assert "casino-top.com" in normalize_text("casino-top [dot] com")
    assert normalize_text("ВЕТ") == "BET"  # cirillico
    assert normalize_text("bo​nus") == "bonus"
    assert "[slot casino]" in normalize_text("🎰")


def test_emoji_meaning_by_platform():
    out = analyse("🔒 partita sicura", platform="telegram")
    assert out["emoji"][0]["significato"] == "partita truccata sicura"
    assert analyse("🔒")["emoji"][0]["significato"] == "partita sicura combine"


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("vai su https://www.bet-top.example.net/x?y=1.", "url", "https://www.bet-top.example.net/x?y=1"),
        ("gioca su vincitutto-bet.com oggi", "dominio", "vincitutto-bet.com"),
        ("canale t.me/vip_quote_it", "canale_telegram", "vip_quote_it"),
        ("codice promo: WELCOME50", "codice_promo", "WELCOME50"),
        ("IBAN IT60 X054 2811 1010 0000 0123 456", "iban", "IT60X0542811101000000123456"),
        ("concessione GAD n. 15001", "concessione_adm", "15001"),
        ("licence OGL/2024/118/0099", "licenza_curacao", "OGL/2024/118/0099"),
    ],
)
def test_entities(text, kind, value):
    assert (kind, value) in {(e.kind, e.value) for e in extract(text)}


def test_no_false_wallets_or_telegram_domain():
    found = {e.kind for e in extract("Conto 12345678901234567890123456 e t.me/canale_test")}
    assert "portafoglio_btc" not in found and ("dominio", "t.me") not in {
        (e.kind, e.value) for e in extract("t.me/canale_test")
    }


def test_checksums():
    assert iban_valid("IT60X0542811101000000123456") and not iban_valid("IT61X0542811101000000123456")
    assert piva_valid("01234567897") and not piva_valid("01234567890")


def test_language_sentiment_summary():
    assert language("Gioca subito e vinci il bonus di benvenuto") == "it"
    assert language("Play now and win your bonus") == "en"
    assert sentiment("Vinci subito!!! bonus enorme")["etichetta"] == "positivo"
    assert sentiment("attenzione truffa, conto bloccato")["etichetta"] == "negativo"
    text = ". ".join(f"Frase numero {i} sul bonus del casino e delle scommesse" for i in range(8)) + "."
    assert len(summary(text, 3)) == 3


def test_no_training_on_telegram():
    examples = [Example(f"testo {i}", i % 2 == 0, "telegram" if i < 5 else "web") for i in range(30)]
    kept, dropped = usable_for_training(examples)
    assert dropped == 5 and all(e.source != "telegram" for e in kept)
    with pytest.raises(TrainingDataError):
        usable_for_training([Example("x", True, "")])
    with pytest.raises(TrainingDataError):
        Classifier("tfidf").train([Example(f"t {i}", bool(i % 2), "telegram") for i in range(40)])


def test_classifier_on_gold_examples():
    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines()]
    model = Classifier("tfidf").train([Example(r["testo"], r["pubblicita_gioco"], r["fonte"]) for r in rows])
    probs = model.predict_proba(
        [
            "Bonus 300% e giri gratis su nuovo-casino-crypto.com, paga in USDT",
            "Ricetta della torta di mele della nonna",
        ]
    )
    assert probs[0] > 0.5 > probs[1]
    again = Classifier.loads(model.dumps())
    assert again.predict_proba(["slot e scommesse con bonus"])[0] == pytest.approx(
        model.predict_proba(["slot e scommesse con bonus"])[0]
    )
    assert model.version.startswith("tfidf-40-")
