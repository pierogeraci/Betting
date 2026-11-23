"""Fase 0: modello dati, coda di lavoro, ruolo ristretto per la raccolta."""

from alembic import op

from core.models import Base

revision = "0001"
down_revision = None

TABELLE_FASE0 = [
    "utente",
    "sessione_utente",
    "sonda",
    "elemento_grezzo",
    "media",
    "estrazione",
    "entita",
    "legame_entita",
    "menzione_entita",
    "sito",
    "snapshot",
    "indicatore",
    "punteggio",
    "revisione",
    "lavoro",
    "adm_caricamento",
    "adm_concessionario",
    "adm_sito_inibito",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in TABELLE_FASE0]
    Base.metadata.create_all(bind, tables=tables)
    op.execute(
        "INSERT INTO sonda (nome, tipo, configurazione, cursore, stato, creato_il) VALUES "
        "('manuale', 'manuale', '{}', '{}', 'attiva', now()), ('adm', 'adm', '{}', '{}', 'attiva', now())"
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind, tables=[Base.metadata.tables[n] for n in reversed(TABELLE_FASE0)])
