"""Fase 2: canali, parole chiave, avvisi; sonde predefinite; origine dei siti."""

from datetime import UTC, datetime

from alembic import op

from core.models import Base

revision = "0003"
down_revision = "0002"
TABLES = ["canale", "parola_chiave", "avviso"]

PAROLE = [
    ("scommesse", "gioco", "it"),
    ("scommessa", "gioco", "it"),
    ("casinò", "gioco", "it"),
    ("casino", "gioco", "en"),
    ("slot", "gioco", "it"),
    ("quote", "gioco", "it"),
    ("bonus benvenuto", "promozione", "it"),
    ("bonus di benvenuto", "promozione", "it"),
    ("free spin", "promozione", "en"),
    ("giri gratis", "promozione", "it"),
    ("betting", "gioco", "en"),
    ("sportsbook", "gioco", "en"),
    ("bookmaker", "gioco", "it"),
    ("poker", "gioco", "it"),
    ("roulette", "gioco", "it"),
    ("crash", "gioco", "en"),
    ("partite truccate", "frode", "it"),
    ("fixed matches", "frode", "en"),
    ("sure win", "frode", "en"),
    ("combine", "frode", "it"),
    ("no kyc", "anonimato", "en"),
    ("senza documenti", "anonimato", "it"),
    ("anonimo", "anonimato", "it"),
    ("bitcoin", "pagamento", "en"),
    ("usdt", "pagamento", "en"),
    ("crypto casino", "gioco", "en"),
    ("deposito minimo", "promozione", "it"),
    ("codice promo", "promozione", "it"),
    ("aams", "titolo", "it"),
    ("adm", "titolo", "it"),
]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in TABLES])
    op.bulk_insert(
        Base.metadata.tables["parola_chiave"],
        [
            {
                "termine": t,
                "categoria": c,
                "lingua": lang,
                "attiva": True,
                "avviso": c == "frode",
                "creato_il": datetime.now(UTC),
            }
            for t, c, lang in PAROLE
        ],
    )
    op.execute(
        "INSERT INTO sonda (nome, tipo, configurazione, cursore, stato, creato_il) VALUES "
        "('telegram', 'telegram', '{\"intervallo_minuti\": 30, \"messaggi_per_canale\": 200, \"scarica_media\": true, \"max_media_mb\": 25, \"max_siti_nuovi\": 30}', '{}', 'in_pausa', now()), "
        "('web', 'web', '{\"intervallo_minuti\": 1440, \"semi\": [], \"profondita\": 1, \"max_pagine\": 40, \"max_siti_nuovi\": 30}', '{}', 'in_pausa', now()), "
        "('tor', 'tor', '{\"intervallo_minuti\": 1440, \"semi\": [], \"profondita\": 1, \"max_pagine\": 30, \"max_siti_nuovi\": 30}', '{}', 'in_pausa', now()) "
        "ON CONFLICT (nome) DO NOTHING"
    )
    # 0001 crea le tabelle dal modello attuale: le colonne possono già esistere.
    op.execute("ALTER TABLE sito ADD COLUMN IF NOT EXISTS fonte_scoperta varchar(40)")
    op.execute("UPDATE sito SET fonte_scoperta = 'manuale' WHERE fonte_scoperta IS NULL")
    op.execute("ALTER TABLE sonda ADD COLUMN IF NOT EXISTS disponibile_dal timestamptz")


def downgrade() -> None:
    op.drop_column("sonda", "disponibile_dal")
    op.drop_column("sito", "fonte_scoperta")
    op.execute("DELETE FROM sonda WHERE nome IN ('telegram', 'web', 'tor')")
    Base.metadata.drop_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in reversed(TABLES)])
