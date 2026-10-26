"""Observaciones de demanda en español (Trends vía HasData y palabras clave de vidIQ).

Revision ID: 0006_demand_observations
Revises: 0005_vidiq_metrics
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_demand_observations"
down_revision = "0005_vidiq_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demand_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("family", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("keyword", sa.String(200), nullable=False),
        sa.Column("geo", sa.String(10), nullable=True),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("reason", sa.String(60), nullable=False),
        sa.Column("result_json", postgresql.JSONB, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("source_data_type", sa.String(20), nullable=False, server_default="PROVIDER"),
        sa.Column("availability", sa.String(20), nullable=False, server_default="AVAILABLE"),
        sa.Column("retention_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_demand_obs_opportunity", "demand_observations", ["opportunity_id", "family"])


def downgrade() -> None:
    op.drop_index("ix_demand_obs_opportunity", table_name="demand_observations")
    op.drop_table("demand_observations")
