"""Analisi del testo delle pubblicità: lingua, emoji, sentiment, riassunto, campi strutturati.

Regole esplicite e dizionari, ripetibili e senza rete. Un modello linguistico locale
(core/llm.py) può arricchire i campi strutturati; l'estratto che giustifica ogni
campo resta sempre nel risultato.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from collectors.base import normalize
from extractors.entities import extract
from extractors.normalize import emoji_in, emoji_meaning, emoji_name, normalize_text

VERSION = "1"

STOP = {
    "it": set(
        "il lo la i gli le un uno una di a da in con su per tra fra e o ma che chi non si ci ne mi ti vi del della dei degli delle al allo alla ai agli alle dal dalla nel nella sul sulla è sono ho hai ha questo questa come più anche".split()
    ),
    "en": set(
        "the a an of to in on for with and or but is are was were be been it this that you your we our they their at by from as not no all more".split()
    ),
    "es": set("el la los las un una de del y o en con por para que es son su sus".split()),
}
POSITIVE = set(
    """vinci vincita vinto vincite bonus gratis regalo sicuro garantito facile subito vincente top migliore super
incredibile esclusivo enorme massimo win winner free guaranteed easy best huge exclusive amazing jackpot profit profitto
guadagna guadagno ricco record""".split()
)
NEGATIVE = set(
    """perso perdita perdi truffa truffe rischio bloccato bannato scam fake lose lost loss blocked banned problema
attenzione ritardo""".split()
)
INTENSIFIERS = set("molto super davvero tantissimo very really mega ultra".split())
PAYMENTS = {
    "carte": ["visa", "mastercard", "carta di credito", "credit card"],
    "bonifico": ["bonifico", "bank transfer", "iban", "sepa"],
    "portafogli": [
        "skrill",
        "neteller",
        "paypal",
        "paysafecard",
        "astropay",
        "muchbetter",
        "perfect money",
        "payeer",
    ],
    "criptovalute": [
        "bitcoin",
        "btc",
        "usdt",
        "tether",
        "ethereum",
        "eth",
        "litecoin",
        "tron",
        "monero",
        "crypto",
        "cripto",
    ],
}
BONUS_RE = re.compile(
    r"(?i)(\d{2,4}\s?%\s*(?:bonus|di bonus)?|bonus[^.!?\n]{0,60}|free\s?spin[s]?[^.\n]{0,40}|giri gratis[^.\n]{0,40}|cashback[^.\n]{0,40})"
)
ITALY_RE = re.compile(
    r"(?i)\b(itali[ae]|italiano|italiani|serie a|€|euro|eur|aams|adm|postepay|spid|codice fiscale)\b|🇮🇹"
)
LANG_HINTS = {
    "it": "il la che per con gioca scommesse vinci bonus deposito quote",
    "en": "the and you your win bet deposit bonus play now",
    "es": "el la que para con apuesta juega bono",
    "de": "der die und mit spielen wetten bonus",
    "ru": "и в на ставки бонус казино",
}


def language(text: str) -> str:
    words = re.findall(r"\w+", (text or "").lower())
    if not words:
        return "sconosciuta"
    if sum(1 for ch in text if "Ѐ" <= ch <= "ӿ") > len(text) * 0.2:
        return "ru"
    scores = {
        lang: sum(1 for w in words if w in set(hints.split()) | STOP.get(lang, set()))
        for lang, hints in LANG_HINTS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "sconosciuta"


def emoji_report(
    text: str, platform: str | None = None, dictionary: dict[tuple[str, str], str] | None = None
) -> list[dict[str, Any]]:
    """Emoji trovate con il significato nel contesto (dizionario per piattaforma, poi generale, poi nome Unicode)."""
    counts = Counter(emoji_in(text))
    out = []
    for ch, n in counts.most_common():
        meaning = None
        if dictionary is not None:
            meaning = dictionary.get((ch, platform or "")) or dictionary.get((ch, ""))
        meaning = meaning or emoji_meaning(ch, platform)
        out.append(
            {
                "emoji": ch,
                "volte": n,
                "significato": meaning,
                "nome": emoji_name(ch),
                "nel_dizionario": meaning is not None,
            }
        )
    return out


def sentiment(text: str) -> dict[str, Any]:
    """Polarità su scala a tre punti con punteggio: parole e emoji del dizionario, intensificatori, punti esclamativi."""
    words = re.findall(r"\w+", normalize(normalize_text(text, emoji=True)))
    score = 0.0
    hits: list[str] = []
    for i, w in enumerate(words):
        boost = 1.5 if i and words[i - 1] in INTENSIFIERS else 1.0
        if w in POSITIVE:
            score += boost
            hits.append(w)
        elif w in NEGATIVE:
            score -= boost
            hits.append(w)
    score += min(text.count("!"), 5) * 0.2
    norm = math.tanh(score / 4)
    label = "positivo" if norm > 0.2 else "negativo" if norm < -0.2 else "neutro"
    return {"etichetta": label, "punteggio": round(norm, 3), "parole": hits[:20]}


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 15]


def summary(text: str, max_sentences: int = 3) -> list[str]:
    """Riassunto estrattivo tipo LexRank: le frasi più simili alle altre."""
    sents = sentences(text)
    if len(sents) <= max_sentences:
        return sents
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    matrix = TfidfVectorizer(min_df=1).fit_transform(sents)
    sim = cosine_similarity(matrix)
    scores = [1.0] * len(sents)
    for _ in range(20):  # iterazione di potenza, smorzamento 0.85
        new = []
        for i in range(len(sents)):
            total = sum(sim[j][i] / max(sum(sim[j]), 1e-9) * scores[j] for j in range(len(sents)) if j != i)
            new.append(0.15 + 0.85 * total)
        scores = new
    best = sorted(sorted(range(len(sents)), key=lambda i: -scores[i])[:max_sentences])
    return [sents[i] for i in best]


def key_phrases(text: str, n: int = 8) -> list[str]:
    lang = language(text)
    stop = STOP.get(lang, set()) | STOP["it"] | STOP["en"]
    words = [w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", normalize(text)) if w not in stop and not w.isdigit()]
    pairs = Counter(" ".join(p) for p in zip(words, words[1:], strict=False))
    single = Counter(words)
    ranked = [p for p, c in pairs.most_common(n) if c > 1] + [w for w, _ in single.most_common(n)]
    return list(dict.fromkeys(ranked))[:n]


def structured(text: str) -> dict[str, Any]:
    """Campi su schema fisso dalla sola applicazione di regole. Ogni valore porta il suo estratto."""
    from collectors.offerta import game_config

    norm_text = normalize_text(text)
    low = normalize(norm_text)
    entities = extract(norm_text)
    games = []
    for code, spec in game_config()["tipi"].items():
        for term in spec["termini"]:
            if re.search(r"(?<![a-z0-9])" + re.escape(normalize(term)) + r"(?![a-z0-9])", low):
                games.append(code)
                break
    payments = sorted(
        {
            k
            for k, terms in PAYMENTS.items()
            for t in terms
            if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low)
        }
    )
    bonus = [m.group(0).strip()[:80] for m in BONUS_RE.finditer(norm_text)][:5]
    italy = [m.group(0) for m in ITALY_RE.finditer(text)][:5]
    domains = [e.value for e in entities if e.kind == "dominio"]
    brands = sorted({d.split(".")[0] for d in domains})[:5]
    return {
        "marchio": brands,
        "url": [e.value for e in entities if e.kind == "url"][:10],
        "domini": domains[:10],
        "giochi": games,
        "pagamenti": payments,
        "bonus": bonus,
        "lingua": language(text),
        "riferimenti_italia": italy,
        "codici_promo": [e.value for e in entities if e.kind == "codice_promo"][:5],
        "portafogli": [e.value for e in entities if e.kind.startswith("portafoglio_")][:5],
        "canali": sum(
            1 for e in entities if e.kind == "canale_telegram"
        ),  # solo il numero: possono essere persone
    }


CHANNEL_LINK = re.compile(
    r"(?i)\b((?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?:s/)?)\+?[A-Za-z0-9_]{4,64}"
)


def mask_channels(text: str) -> str:
    """I nomi dopo t.me/ possono essere account di persone: nel testo conservato diventano un segnaposto."""
    return CHANNEL_LINK.sub(r"\1[canale]", text or "")


def analyse(
    text: str, platform: str | None = None, emoji_dictionary: dict[tuple[str, str], str] | None = None
) -> dict[str, Any]:
    raw_clean = normalize_text(text, platform)
    clean = mask_channels(raw_clean)
    return {
        "versione": VERSION,
        "testo_normalizzato": clean[:5000],
        "lingua": language(text),
        "emoji": emoji_report(text, platform, emoji_dictionary),
        "sentiment": sentiment(text),
        "riassunto": summary(clean),
        "parole_chiave": key_phrases(clean),
        "campi": structured(text)
        | {"canali": sum(1 for e in extract(raw_clean) if e.kind == "canale_telegram")},
        "entita": [
            {"tipo": e.kind, "valore": e.value, "certezza": e.certainty}
            for e in extract(clean)
            if e.kind != "canale_telegram"
        ][:100],
    }
