"""M0: esquema inicial del subconjunto necesario para la demo.

Revision ID: 0001_m0_initial
Revises:
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_m0_initial"
down_revision = None
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "niches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_name_es", sa.String(200), nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("exclusions_json", postgresql.JSONB, nullable=False),
        sa.Column("taxonomy_version", sa.String(40), nullable=False),
        sa.Column("source_data_type", sa.String(20), nullable=False),
        _created_at(),
    )
    op.create_table(
        "formats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_name_es", sa.String(200), nullable=False),
        sa.Column("story_structure", sa.Text, nullable=False),
        sa.Column("visual_grammar", sa.Text, nullable=False),
        sa.Column("audio_grammar", sa.Text, nullable=False),
        sa.Column("min_assets", sa.Integer, nullable=True),
        sa.Column("requirements_json", postgresql.JSONB, nullable=False),
        sa.Column("taxonomy_version", sa.String(40), nullable=False),
        sa.Column("source_data_type", sa.String(20), nullable=False),
        _created_at(),
    )
    op.create_table(
        "channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("youtube_channel_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title_current", sa.String(200), nullable=False),
        sa.Column("subscriber_count", sa.Integer, nullable=True),
        sa.Column("subscriber_band", sa.String(40), nullable=False),
        sa.Column("language_state", sa.String(20), nullable=False),
        sa.Column("region_declared", sa.String(10), nullable=True),
        sa.Column("provider", sa.String(60), nullable=False),
        _ts("observed_at"),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("source_data_type", sa.String(20), nullable=False),
        _created_at(),
    )
    op.create_table(
        "videos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("youtube_video_id", sa.String(64), nullable=False, unique=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        _ts("published_at"),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("video_type", sa.String(10), nullable=False),
        sa.Column("video_type_evidence", sa.String(200), nullable=False),
        sa.Column("language_state", sa.String(20), nullable=False),
        sa.Column("language_confidence", sa.String(20), nullable=False),
        sa.Column("view_count", sa.Integer, nullable=True),
        sa.Column("url", sa.String(300), nullable=True),
        sa.Column("provider", sa.String(60), nullable=False),
        _ts("observed_at"),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("source_data_type", sa.String(20), nullable=False),
        sa.Column("availability", sa.String(20), nullable=False),
        _created_at(),
    )
    op.create_index(
        "ix_videos_published_type_lang", "videos", ["published_at", "video_type", "language_state"]
    )
    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("niche_id", sa.String(36), sa.ForeignKey("niches.id"), nullable=False),
        sa.Column("format_id", sa.String(36), sa.ForeignKey("formats.id"), nullable=False),
        sa.Column("target_lang", sa.String(10), nullable=False),
        sa.Column("video_type", sa.String(10), nullable=False),
        sa.Column("source_languages_json", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("owner_notes", sa.Text, nullable=True),
        _created_at(),
        sa.UniqueConstraint(
            "niche_id", "format_id", "target_lang", "video_type", name="uq_opportunity_key"
        ),
    )
    op.create_table(
        "opportunity_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id"), nullable=False
        ),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("evidence_text", sa.Text, nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        _ts("observed_at"),
        sa.Column("support_strength", sa.String(20), nullable=False),
        sa.Column("availability", sa.String(20), nullable=False),
        sa.Column("source_data_type", sa.String(20), nullable=False),
    )
    op.create_index(
        "ix_opportunity_evidence_opportunity_id", "opportunity_evidence", ["opportunity_id"]
    )
    op.create_table(
        "research_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("params_json", postgresql.JSONB, nullable=False),
        sa.Column("algorithm_version", sa.String(20), nullable=False),
        sa.Column("policy_mode", sa.String(20), nullable=False),
        _ts("started_at", nullable=True),
        _ts("finished_at", nullable=True),
        sa.Column("errors_json", postgresql.JSONB, nullable=False),
        sa.Column("coverage_json", postgresql.JSONB, nullable=False),
        sa.Column("budget_json", postgresql.JSONB, nullable=False),
        _created_at(),
    )
    op.create_index("ix_research_runs_status", "research_runs", ["status"])
    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id"), nullable=False
        ),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("research_runs.id"), nullable=True),
        sa.Column("evaluation_version", sa.Integer, nullable=False),
        sa.Column("international_json", postgresql.JSONB, nullable=False),
        sa.Column("spanish_json", postgresql.JSONB, nullable=False),
        sa.Column("feasibility_json", postgresql.JSONB, nullable=False),
        sa.Column("scores_json", postgresql.JSONB, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("reason_codes_json", postgresql.JSONB, nullable=False),
        sa.Column("recommendation", sa.String(40), nullable=False),
        sa.Column("metric_policy_state", sa.String(40), nullable=False),
        sa.Column("source_data_type", sa.String(20), nullable=False),
        _ts("observed_at"),
        _created_at(),
        sa.UniqueConstraint("opportunity_id", "evaluation_version", name="uq_evaluation_version"),
    )
    op.create_index("ix_evaluations_opportunity_id", "evaluations", ["opportunity_id"])
    op.create_table(
        "run_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("research_runs.id"), nullable=False),
        sa.Column("task_type", sa.String(40), nullable=False),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        _ts("next_attempt_at"),
        _ts("locked_at", nullable=True),
        sa.Column("payload_json", postgresql.JSONB, nullable=False),
        sa.Column("result_json", postgresql.JSONB, nullable=False),
        sa.Column("error_class", sa.String(60), nullable=True),
        sa.UniqueConstraint("run_id", "dedupe_key", name="uq_run_task_dedupe"),
    )
    op.create_index("ix_run_tasks_queue", "run_tasks", ["status", "next_attempt_at"])
    op.create_table(
        "policy_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("capability", sa.String(60), nullable=False),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approval_ref", sa.String(200), nullable=True),
        sa.Column("reviewed_by", sa.String(120), nullable=True),
        _ts("effective_at", nullable=True),
        _ts("expires_at", nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("actor", sa.String(60), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("object_type", sa.String(40), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False),
        sa.Column("details_redacted_json", postgresql.JSONB, nullable=False),
        _created_at(),
    )


def downgrade() -> None:
    for table in [
        "audit_events",
        "policy_approvals",
        "run_tasks",
        "evaluations",
        "research_runs",
        "opportunity_evidence",
        "opportunities",
        "videos",
        "channels",
        "formats",
        "niches",
    ]:
        op.drop_table(table)
