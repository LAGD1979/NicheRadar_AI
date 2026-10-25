"""M3: modelos de costo versionados.

Revision ID: 0004_m3_decisions
Revises: 0003_m2_spanish_market
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_m3_decisions"
down_revision = "0003_m2_spanish_market"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("params_json", postgresql.JSONB, nullable=False),
        sa.Column("scenarios_json", postgresql.JSONB, nullable=False),
        sa.Column("missing_json", postgresql.JSONB, nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("opportunity_id", "version", name="uq_cost_model_version"),
    )
    op.create_index("ix_cost_models_opportunity_id", "cost_models", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_cost_models_opportunity_id", table_name="cost_models")
    op.drop_table("cost_models")
