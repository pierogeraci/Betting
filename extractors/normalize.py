"""Normalizzazione del testo delle pubblicità.

Forme Unicode, caratteri sosia (lettere cirilliche o matematiche al posto di
quelle latine), separatori inseriti per offuscare ("s.c.o.m.m.e.s.s.e",
"b e t"), emoji convertite nel loro nome o nel significato del dizionario.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

# Sosia più comuni: cirillico e greco che sembrano latino.
CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "к": "k",
        "м": "m",
        "т": "t",
        "в": "b",
        "н": "h",
        "і": "i",
        "ј": "j",
        "ѕ": "s",
        "ԁ": "d",
        "ɡ": "g",
        "ո": "n",
        "ս": "u",
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "У": "Y",
        "α": "a",
        "ο": "o",
        "ρ": "p",
        "ν": "v",
        "τ": "t",
        "ι": "i",
        "κ": "k",
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Ζ": "Z",
        "Η": "H",
        "Ι": "I",
        "Κ": "K",
        "Μ": "M",
        "Ν": "N",
        "Ο": "O",
        "Ρ": "P",
        "Τ": "T",
        "Υ": "Y",
        "Χ": "X",
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "＠": "@",
        "．": ".",
        "／": "/",
        "：": ":",
    }
)
ZERO_WIDTH = re.compile("[​-‏⁠-⁤﻿­]")
# Lettere singole separate da punti, trattini, asterischi o spazi: "s.c.o.m.m.e.s.s.e".
SPACED = re.compile(r"(?<!\w)((?:[A-Za-zÀ-ÿ][\s.\-*_·•|]{1,2}){3,}[A-Za-zÀ-ÿ])(?!\w)")
# "dot" e "punto" scritti per nascondere un dominio: "sito [dot] com", "sito(.)com".
DOT_WORDS = re.compile(
    r"(?i)\s*(?:\[\s*(?:dot|punto|\.)\s*\]|\(\s*(?:dot|punto|\.)\s*\)|\{\s*(?:dot|punto|\.)\s*\})\s*"
)
EMOJI_CONFIG = Path(__file__).resolve().parent.parent / "config" / "emoji.yaml"


@lru_cache
def emoji_dictionary() -> dict:
    if not EMOJI_CONFIG.exists():
        return {}
    return yaml.safe_load(EMOJI_CONFIG.read_text(encoding="utf-8")) or {}


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (
        (0x1F000 <= cp <= 0x1FAFF)
        or (0x2600 <= cp <= 0x27BF)
        or (0x2B00 <= cp <= 0x2BFF)
        or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D)
    )


def emoji_meaning(ch: str, platform: str | None = None) -> str | None:
    """Significato nel dizionario (per piattaforma, poi generale), altrimenti None."""
    data = emoji_dictionary().get("emoji", {})
    entry = data.get(ch)
    if not entry:
        return None
    if platform and isinstance(entry.get("piattaforme"), dict) and entry["piattaforme"].get(platform):
        return entry["piattaforme"][platform]
    return entry.get("significato")


def emoji_name(ch: str) -> str:
    try:
        return unicodedata.name(ch).lower()
    except ValueError:
        return ""


def replace_emoji(text: str, platform: str | None = None) -> str:
    out = []
    for ch in text:
        if is_emoji(ch):
            meaning = emoji_meaning(ch, platform)
            name = meaning or emoji_name(ch)
            out.append(f" [{name}] " if name else " ")
        elif ch in "️‍":
            continue
        else:
            out.append(ch)
    return "".join(out)


def _join_spaced(match: re.Match[str]) -> str:
    return re.sub(r"[\s.\-*_·•|]", "", match.group(1))


def normalize_text(text: str, platform: str | None = None, emoji: bool = True) -> str:
    """Testo pronto per parole chiave ed estrazione. Non cambia il senso, toglie l'offuscamento."""
    text = unicodedata.normalize("NFKC", text or "")
    text = ZERO_WIDTH.sub("", text)
    text = text.translate(CONFUSABLES)
    text = DOT_WORDS.sub(".", text)
    text = SPACED.sub(_join_spaced, text)
    if emoji:
        text = replace_emoji(text, platform)
    return re.sub(r"[ \t]+", " ", text).strip()


def emoji_in(text: str) -> list[str]:
    return [ch for ch in text or "" if is_emoji(ch)]
