"""M2: anotaciones de video, planes de búsqueda en español y vínculo de coincidencias.

Revision ID: 0003_m2_spanish_market
Revises: 0002_m1_ingestion
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_m2_spanish_market"
down_revision = "0002_m1_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("source_queries", sa.Column("opportunity_id", sa.String(36), nullable=True))
    op.create_index("ix_source_queries_opportunity_id", "source_queries", ["opportunity_id"])
    op.create_foreign_key(
        "fk_source_queries_opportunity_id", "source_queries", "opportunities",
        ["opportunity_id"], ["id"],
    )
    op.add_column("discovery_matches", sa.Column("opportunity_id", sa.String(36), nullable=True))
    op.add_column("discovery_matches", sa.Column("reviewed_by", sa.String(120), nullable=True))
    op.create_foreign_key(
        "fk_discovery_matches_opportunity_id", "discovery_matches", "opportunities",
        ["opportunity_id"], ["id"],
    )
    op.create_index("ix_discovery_matches_opportunity_id", "discovery_matches", ["opportunity_id"])

    op.create_table(
        "video_annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("same_format_confidence", sa.String(10), nullable=False),
        sa.Column("label_source", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(60), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("reviewed_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_video_annotations_video_id", "video_annotations", ["video_id"])
    op.create_index("ix_video_annotations_opportunity_id", "video_annotations", ["opportunity_id"])

    op.create_table(
        "spanish_search_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("plan_json", postgresql.JSONB, nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("model_version", sa.String(60), nullable=True),
        sa.Column("source_ids_json", postgresql.JSONB, nullable=False),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_spanish_search_plans_opportunity_id", "spanish_search_plans", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_spanish_search_plans_opportunity_id", table_name="spanish_search_plans")
    op.drop_table("spanish_search_plans")
    op.drop_index("ix_video_annotations_opportunity_id", table_name="video_annotations")
    op.drop_index("ix_video_annotations_video_id", table_name="video_annotations")
    op.drop_table("video_annotations")
    op.drop_index("ix_discovery_matches_opportunity_id", table_name="discovery_matches")
    op.drop_constraint("fk_discovery_matches_opportunity_id", "discovery_matches", type_="foreignkey")
    op.drop_column("discovery_matches", "reviewed_by")
    op.drop_column("discovery_matches", "opportunity_id")
    op.drop_constraint("fk_source_queries_opportunity_id", "source_queries", type_="foreignkey")
    op.drop_index("ix_source_queries_opportunity_id", table_name="source_queries")
    op.drop_column("source_queries", "opportunity_id")
    op.drop_column("opportunities", "last_evaluated_at")
