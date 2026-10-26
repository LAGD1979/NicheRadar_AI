"""Modelo de IA elegido por función (asistente, clasificación, plan de búsqueda).

Revision ID: 0008_ai_selections
Revises: 0007_match_ai_suggestions
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_ai_selections"
down_revision = "0007_match_ai_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_selections",
        sa.Column("function_id", sa.String(30), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("updated_by", sa.String(60), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_selections")
