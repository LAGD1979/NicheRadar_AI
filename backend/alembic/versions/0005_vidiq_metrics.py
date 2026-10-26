"""vidIQ: métricas de proveedor por video, con procedencia y purga junto al video.

Revision ID: 0005_vidiq_metrics
Revises: 0004_m3_decisions
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_vidiq_metrics"
down_revision = "0004_m3_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("provider_metrics", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "provider_metrics")
