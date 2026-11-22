"""Estrazione strutturata con un modello linguistico in locale (Ollama), su schema fisso.

Facoltativa: se il servizio non risponde si usano le sole regole. I dati non escono
dalla macchina. Il modello non si addestra né si rifinisce su alcun dato raccolto.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def _url() -> str:
    return os.environ.get("OLLAMA_URL", "")


MODEL = os.environ.get("OLLAMA_MODELLO", "qwen2.5:7b-instruct")
SCHEMA = {
    "type": "object",
    "properties": {
        "marchio": {"type": "array", "items": {"type": "string"}},
        "url": {"type": "array", "items": {"type": "string"}},
        "giochi": {"type": "array", "items": {"type": "string"}},
        "pagamenti": {"type": "array", "items": {"type": "string"}},
        "bonus": {"type": "array", "items": {"type": "string"}},
        "lingua": {"type": "string"},
        "riferimenti_italia": {"type": "array", "items": {"type": "string"}},
        "estratto": {"type": "string"},
    },
    "required": ["marchio", "giochi", "pagamenti", "lingua", "estratto"],
}
PROMPT = (
    "Estrai dalla pubblicità seguente i campi richiesti, solo se compaiono nel testo. "
    "Non inventare. Non indicare nomi di persone. In 'estratto' copia la frase che giustifica la risposta.\n\nTesto:\n{text}"
)


def available() -> bool:
    return bool(_url())


def extract_fields(text: str, timeout: int = 60) -> dict[str, Any] | None:
    if not _url():
        return None
    body = json.dumps(
        {
            "model": MODEL,
            "prompt": PROMPT.format(text=text[:6000]),
            "format": SCHEMA,
            "stream": False,
            "options": {"temperature": 0},
        }
    ).encode()
    request = urllib.request.Request(
        _url().rstrip("/") + "/api/generate", data=body, headers={"Content-Type": "application/json"}
    )  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - servizio interno configurato
            data = json.loads(response.read())
        fields = json.loads(data.get("response") or "{}")
    except Exception:  # noqa: BLE001 - servizio facoltativo
        return None
    if not isinstance(fields, dict):
        return None
    fields["modello"] = MODEL
    return fields
