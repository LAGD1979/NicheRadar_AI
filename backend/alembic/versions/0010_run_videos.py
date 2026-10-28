"""Videos observados por cada corrida, para listar lo que trajo una corrida concreta.

Revision ID: 0010_run_videos
Revises: 0009_scheduler_watchlist_alerts
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_run_videos"
down_revision = "0009_scheduler_watchlist_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_videos",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), primary_key=True),
    )
    op.create_index("ix_run_videos_video_id", "run_videos", ["video_id"])
    # Relleno de lo ya guardado: solo se conoce la ÚLTIMA corrida que vio cada video, así que un
    # video visto por dos corridas antiguas queda asociado únicamente a la más reciente.
    op.execute(
        """
        INSERT INTO run_videos (run_id, video_id)
        SELECT r.id, v.id
        FROM videos v
        JOIN research_runs r ON r.id = v.provider_metrics->'vidiq'->>'run_id'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_run_videos_video_id", table_name="run_videos")
    op.drop_table("run_videos")
