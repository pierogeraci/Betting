"""Indirizzi delle fonti ufficiali, letti da config/fonti.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_PATH = Path(__file__).resolve().parent.parent / "config" / "fonti.yaml"


@lru_cache
def _load() -> dict:
    if not _PATH.exists():
        return {}
    return yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}


def adm_sources() -> dict[str, str]:
    data = _load().get("adm") or {}
    return {"concessionari": data.get("concessionari") or "", "siti_inibiti": data.get("siti_inibiti") or ""}
