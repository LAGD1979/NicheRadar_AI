"""M1: procedencia y retención en canales/videos; consultas, coincidencias y uso de cuota.

Revision ID: 0002_m1_ingestion
Revises: 0001_m0_initial
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_m1_ingestion"
down_revision = "0001_m0_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("uploads_playlist_id", sa.String(64), nullable=True))
    op.add_column(
        "channels",
        sa.Column("owner_authorized", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "channels",
        sa.Column("retention_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "videos",
        sa.Column("owner_authorized", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("videos", sa.Column("retention_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("videos", sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "source_queries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("research_runs.id"), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("language_requested", sa.String(20), nullable=False),
        sa.Column("region", sa.String(10), nullable=True),
        sa.Column("query_text", sa.String(300), nullable=False),
        sa.Column("window_code", sa.String(10), nullable=False),
        sa.Column("params_json", postgresql.JSONB, nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_count", sa.Integer, nullable=False),
        sa.Column("pages", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("warnings_json", postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_source_queries_run_id", "source_queries", ["run_id"])
    op.create_table(
        "discovery_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("research_runs.id"), nullable=False),
        sa.Column("query_id", sa.String(36), sa.ForeignKey("source_queries.id"), nullable=False),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("strategy", sa.String(40), nullable=False),
        sa.Column("match_quality", sa.String(20), nullable=False),
        sa.Column("is_spanish_market", sa.Boolean, nullable=False),
        sa.UniqueConstraint("query_id", "video_id", name="uq_discovery_match"),
    )
    op.create_index("ix_discovery_matches_run_id", "discovery_matches", ["run_id"])
    op.create_index("ix_discovery_matches_video_id", "discovery_matches", ["video_id"])
    op.create_table(
        "provider_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("endpoint", sa.String(40), nullable=False),
        sa.Column("quota_bucket", sa.String(40), nullable=False),
        sa.Column("units", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index(
        "ix_provider_usage_bucket_time", "provider_usage", ["provider", "quota_bucket", "started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_provider_usage_bucket_time", table_name="provider_usage")
    op.drop_table("provider_usage")
    op.drop_index("ix_discovery_matches_video_id", table_name="discovery_matches")
    op.drop_index("ix_discovery_matches_run_id", table_name="discovery_matches")
    op.drop_table("discovery_matches")
    op.drop_index("ix_source_queries_run_id", table_name="source_queries")
    op.drop_table("source_queries")
    for column in ("last_refreshed_at", "retention_deadline", "owner_authorized"):
        op.drop_column("videos", column)
    for column in ("last_refreshed_at", "retention_deadline", "owner_authorized", "uploads_playlist_id"):
        op.drop_column("channels", column)
