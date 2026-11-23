"""Lettura di config/trust_index.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PATH = Path(__file__).resolve().parent.parent / "config" / "trust_index.yaml"


@lru_cache
def load_rules(path: str | None = None) -> dict[str, Any]:
    data = yaml.safe_load(Path(path or PATH).read_text(encoding="utf-8"))
    if not data.get("version"):
        raise ValueError("config/trust_index.yaml senza campo version")
    return data


def level(value: float, levels: list[dict[str, Any]]) -> str:
    """Livello per soglie: `sotto` è esclusiva, `fino_a` inclusiva, l'ultimo livello prende il resto."""
    for item in levels:
        if "sotto" in item and value < item["sotto"]:
            return item["livello"]
        if "fino_a" in item and value <= item["fino_a"]:
            return item["livello"]
        if "sotto" not in item and "fino_a" not in item:
            return item["livello"]
    return levels[-1]["livello"]
