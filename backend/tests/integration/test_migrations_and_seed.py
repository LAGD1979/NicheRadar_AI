from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db import models as m
from app.demo.seed import load_fixture, seed_fixture
from tests.conftest import truncate_all


def test_migrations_match_models(test_database_url: str, empty_db: Session) -> None:
    """El esquema migrado coincide con los modelos: no hay diferencias pendientes."""
    context = MigrationContext.configure(empty_db.connection())
    diff = compare_metadata(context, m.Base.metadata)
    assert diff == []


def test_seed_is_idempotent(empty_db: Session) -> None:
    # T21: repetir el seed no duplica filas.
    data = load_fixture()
    first = seed_fixture(empty_db, data)
    empty_db.commit()
    second = seed_fixture(empty_db, data)
    empty_db.commit()
    assert first == second
    assert empty_db.scalar(select(func.count()).select_from(m.Opportunity)) == 8
    assert empty_db.scalar(select(func.count()).select_from(m.Video)) == 20


def test_nulls_and_zeros_are_kept_distinct(seeded_db: Session) -> None:
    # T02: suscriptores NULL no es cero; cero real sí se conserva.
    hidden = seeded_db.get(m.Channel, "syn-ch-05")
    zero = seeded_db.get(m.Channel, "syn-ch-04")
    assert hidden is not None and hidden.subscriber_count is None
    assert zero is not None and zero.subscriber_count == 0


def test_every_record_is_labelled_synthetic(seeded_db: Session) -> None:
    # T22: ningún registro del demo aparece como dato real.
    videos = seeded_db.scalars(select(m.Video.source_data_type).distinct()).all()
    evaluations = seeded_db.scalars(select(m.Evaluation.source_data_type).distinct()).all()
    assert set(videos) == {"SYNTHETIC"}
    assert set(evaluations) == {"SYNTHETIC"}


def test_language_conflict_is_unknown_not_forced(seeded_db: Session) -> None:
    # T04: título en español con audio portugués queda en conflicto, no se fuerza idioma.
    video = seeded_db.scalar(select(m.Video).where(m.Video.youtube_video_id == "SYNV17"))
    assert video is not None
    assert video.language_state == "UNKNOWN"
    assert video.language_confidence == "CONFLICT"


def test_short_ambiguous_video_is_unknown(seeded_db: Session) -> None:
    video = seeded_db.scalar(select(m.Video).where(m.Video.youtube_video_id == "SYNV19"))
    assert video is not None
    assert video.video_type == "UNKNOWN"
    assert video.duration_seconds == 100


def test_truncate_helper_empties_tables(seeded_db: Session) -> None:
    truncate_all(seeded_db)
    assert seeded_db.scalar(select(func.count()).select_from(m.Niche)) == 0
