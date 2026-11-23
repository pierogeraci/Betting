"""Fase 4: registri pubblici, legal entity, eventi sportivi e quote."""

from alembic import op

from core.models import Base

revision = "0005"
down_revision = "0004"
TABLES = ["registro_voce", "legal_entity", "evento_sportivo", "quota_evento"]


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in TABLES])


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in reversed(TABLES)])
