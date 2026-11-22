"""Fase 3: etichette, dizionario delle emoji, valutazioni, indici per la ricerca nei contenuti."""

from pathlib import Path

import yaml
from alembic import op

from core.models import Base

revision = "0004"
down_revision = "0003"
TABLES = ["etichetta", "emoji", "valutazione", "modello"]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in TABLES])
    data = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "config" / "emoji.yaml").read_text(encoding="utf-8")
    )
    rows = []
    for char, entry in (data.get("emoji") or {}).items():
        rows.append(
            {
                "carattere": char,
                "piattaforma": "",
                "significato": entry["significato"],
                "categoria": entry.get("categoria", ""),
                "occorrenze": 0,
            }
        )
        for platform, meaning in (entry.get("piattaforme") or {}).items():
            rows.append(
                {
                    "carattere": char,
                    "piattaforma": platform,
                    "significato": meaning,
                    "categoria": entry.get("categoria", ""),
                    "occorrenze": 0,
                }
            )
    if rows:
        op.bulk_insert(Base.metadata.tables["emoji"], rows)
    op.execute(
        "CREATE INDEX IF NOT EXISTS estrazione_testo_fts ON estrazione USING gin (to_tsvector('simple', testo))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS elemento_testo_fts ON elemento_grezzo USING gin (to_tsvector('simple', coalesce(contenuto, '')))"
    )
    op.execute("CREATE INDEX IF NOT EXISTS estrazione_elemento ON estrazione (elemento_grezzo_id, tipo)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS estrazione_elemento")
    op.execute("DROP INDEX IF EXISTS elemento_testo_fts")
    op.execute("DROP INDEX IF EXISTS estrazione_testo_fts")
    Base.metadata.drop_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in reversed(TABLES)])
