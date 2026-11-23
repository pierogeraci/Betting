"""Fase 1: puntate, legami tra siti (domini gemelli)."""

from alembic import op

from core.models import Base

revision = "0002"
down_revision = "0001"
TABLES = ["puntata", "legame_sito"]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in TABLES])


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in reversed(TABLES)])
