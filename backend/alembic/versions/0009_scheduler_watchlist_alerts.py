"""M5: trabajos programados, seguimiento (watchlist), acciones de revisión y alertas.

Revision ID: 0009_scheduler_watchlist_alerts
Revises: 0008_ai_selections
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_scheduler_watchlist_alerts"
down_revision = "0008_ai_selections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("job_type", sa.String(40), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("interval_hours", sa.Integer, nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_id", sa.String(36)),
        sa.Column("updated_by", sa.String(60), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(36),
            sa.ForeignKey("opportunities.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("pilot_plan_json", postgresql.JSONB, nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB, nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "review_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(36),
            sa.ForeignKey("opportunities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("actor", sa.String(60), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id")),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("details_json", postgresql.JSONB, nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alerts_open", "alerts", ["acknowledged_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_alerts_open", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("review_actions")
    op.drop_table("watchlists")
    op.drop_table("scheduled_jobs")
