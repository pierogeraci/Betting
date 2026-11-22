"""Prepara la prova su dati reali: inserisce gli URL di PROVA_URLS (al massimo tre)."""

from __future__ import annotations

import os
import sys

from core import intake
from core.db import session_scope

MAX_URLS = 3


def main() -> None:
    urls = [u.strip() for u in os.environ.get("PROVA_URLS", "").split(",") if u.strip()]
    if not urls:
        sys.exit("Imposta PROVA_URLS in .env: al massimo tre URL separati da virgola.")
    if len(urls) > MAX_URLS:
        sys.exit(f"La prova reale ha un limite di {MAX_URLS} pagine: ne hai indicate {len(urls)}.")
    with session_scope() as session:
        for url in urls:
            result = intake.submit_url(session, url)
            print(f"inserito {result.url.url} → sito {result.site.dominio} (lavoro {result.job.id})")


if __name__ == "__main__":
    main()
