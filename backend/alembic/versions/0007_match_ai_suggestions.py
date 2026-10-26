"""Sugerencias de la IA para la revisión de competidores (nunca cuentan como revisión).

Revision ID: 0007_match_ai_suggestions
Revises: 0006_demand_observations
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_match_ai_suggestions"
down_revision = "0006_demand_observations"
branch_labels = None
depends_on = None

COLUMNS = (
    ("ai_quality", sa.String(20)),
    ("ai_confidence", sa.String(10)),
    ("ai_reason", sa.String(300)),
    ("ai_model", sa.String(60)),
    ("ai_prompt_version", sa.String(20)),
    ("ai_suggested_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column("discovery_matches", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _kind in reversed(COLUMNS):
        op.drop_column("discovery_matches", name)
