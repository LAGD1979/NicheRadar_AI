"""Ingesta M1 contra PostgreSQL con una fuente falsa (sin red)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m
from app.providers.base import ProviderAuthError
from app.services import quota_service
from app.services.ingestion_service import (
    QueryPlan,
    load_channel_uploads,
    run_discovery,
)
from tests.fakes import FakeSource, synthetic_channel, synthetic_hit, synthetic_video

NOW = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)


def _run(session: Session, run_id: str) -> None:
    session.add(
        m.ResearchRun(
            id=run_id,
            kind="discovery",
            status="RUNNING",
            params_json={},
            algorithm_version="test",
            policy_mode="restricted",
            errors_json=[],
            coverage_json={},
            budget_json={},
        )
    )
    session.flush()


def _plan(query: str, language: str = "es", window: str = "0-7") -> QueryPlan:
    return QueryPlan(language=language, query=query, window=window)


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def test_same_video_from_two_queries_is_one_row_with_two_matches(empty_db: Session) -> None:
    # T01: un video, dos coincidencias de búsqueda, procedencia separada.
    _run(empty_db, "run-t01")
    source = FakeSource(
        hits={
            "historia": [synthetic_hit("SYNV01", "SYNCH01")],
            "mapas": [synthetic_hit("SYNV01", "SYNCH01")],
        },
        videos=[synthetic_video("SYNV01", "SYNCH01")],
        channels=[synthetic_channel("SYNCH01")],
    )
    outcome = run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-t01",
        plans=[_plan("historia"), _plan("mapas")],
        completed_keys=set(),
        max_search_calls=5,
        pages_per_query=1,
        now=NOW,
    )
    empty_db.commit()
    assert outcome.outcome == "COMPLETED"
    assert empty_db.scalar(select(func.count()).select_from(m.Video)) == 1
    assert empty_db.scalar(select(func.count()).select_from(m.DiscoveryMatch)) == 2
    assert empty_db.scalar(select(func.count()).select_from(m.SourceQuery)) == 2


def test_hidden_subscribers_are_null_and_zero_stays_zero(empty_db: Session) -> None:
    # T02: suscriptores ocultos → NULL; cero real → 0.
    _run(empty_db, "run-t02")
    source = FakeSource(
        hits={"q": [synthetic_hit("SYNV01", "SYNCH05"), synthetic_hit("SYNV02", "SYNCH04")]},
        videos=[synthetic_video("SYNV01", "SYNCH05"), synthetic_video("SYNV02", "SYNCH04")],
        channels=[
            synthetic_channel("SYNCH05", subs=None, hidden=True),
            synthetic_channel("SYNCH04", subs=0),
        ],
    )
    run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-t02",
        plans=[_plan("q")],
        completed_keys=set(),
        max_search_calls=2,
        pages_per_query=1,
        now=NOW,
    )
    empty_db.commit()
    hidden = empty_db.scalars(
        select(m.Channel).where(m.Channel.youtube_channel_id == "SYNCH05")
    ).one()
    zero = empty_db.scalars(
        select(m.Channel).where(m.Channel.youtube_channel_id == "SYNCH04")
    ).one()
    assert hidden.subscriber_count is None and hidden.subscriber_band == "UNKNOWN"
    assert zero.subscriber_count == 0 and zero.subscriber_band == "[0,1000)"


def test_language_conflict_from_api_is_stored_unknown(empty_db: Session) -> None:
    # T04: audio portugués con metadatos en inglés → UNKNOWN/CONFLICT.
    _run(empty_db, "run-t04")
    video = synthetic_video("SYNV03", "SYNCH01", audio="pt", meta="en")
    source = FakeSource(
        hits={"q": [synthetic_hit("SYNV03", "SYNCH01")]},
        videos=[video],
        channels=[synthetic_channel("SYNCH01")],
    )
    run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-t04",
        plans=[_plan("q")],
        completed_keys=set(),
        max_search_calls=1,
        pages_per_query=1,
        now=NOW,
    )
    empty_db.commit()
    stored = empty_db.scalars(select(m.Video).where(m.Video.youtube_video_id == "SYNV03")).one()
    assert (stored.language_state, stored.language_confidence) == ("UNKNOWN", "CONFLICT")


def test_quota_budget_pauses_and_keeps_progress(empty_db: Session) -> None:
    # Presupuesto de 150 u. con 90 % blando = 135: la primera búsqueda (100 u.) cabe, la segunda no.
    _run(empty_db, "run-quota")
    settings = _settings(youtube_daily_units_limit=150, youtube_daily_units_soft_pct=0.9)
    source = FakeSource(hits={"a": [], "b": []})
    outcome = run_discovery(
        empty_db,
        source,
        settings,
        run_id="run-quota",
        plans=[_plan("a"), _plan("b")],
        completed_keys=set(),
        max_search_calls=5,
        pages_per_query=1,
        now=NOW,
    )
    empty_db.commit()
    assert outcome.outcome == "PAUSED_QUOTA"
    assert outcome.completed == ["es|0-7||a"]
    assert quota_service.units_used_today(empty_db, NOW) == 100


def test_resume_skips_completed_queries(empty_db: Session) -> None:
    _run(empty_db, "run-resume")
    source = FakeSource(
        hits={"a": [synthetic_hit("SYNV01", "SYNCH01")]},
        videos=[synthetic_video("SYNV01", "SYNCH01")],
        channels=[synthetic_channel("SYNCH01")],
    )
    first, second = _plan("a"), _plan("b")
    outcome = run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-resume",
        plans=[first, second],
        completed_keys={first.key},
        max_search_calls=5,
        pages_per_query=1,
        now=NOW,
    )
    empty_db.commit()
    assert [p.query for p in source.search_params] == ["b"]
    assert second.key in outcome.completed


def test_search_budget_stops_with_partial(empty_db: Session) -> None:
    _run(empty_db, "run-budget")
    source = FakeSource()
    outcome = run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-budget",
        plans=[_plan("a"), _plan("b")],
        completed_keys=set(),
        max_search_calls=1,
        pages_per_query=1,
        now=NOW,
    )
    assert outcome.outcome == "PARTIAL"
    assert outcome.errors[0]["code"] == "BUDGET_SEARCH_CALLS"


def test_auth_error_fails_the_run(empty_db: Session) -> None:
    _run(empty_db, "run-auth")
    source = FakeSource(search_error=ProviderAuthError("clave rechazada"))
    outcome = run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-auth",
        plans=[_plan("a"), _plan("b")],
        completed_keys=set(),
        max_search_calls=5,
        pages_per_query=1,
        now=NOW,
    )
    assert outcome.outcome == "FAILED"
    assert outcome.completed == []


def test_pagination_uses_second_page_within_page_budget(empty_db: Session) -> None:
    # T05: el siguiente page token se pide y cada página cuesta cuota.
    _run(empty_db, "run-pages")
    source = FakeSource(second_page=True)
    run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-pages",
        plans=[_plan("a")],
        completed_keys=set(),
        max_search_calls=5,
        pages_per_query=2,
        now=NOW,
    )
    empty_db.commit()
    assert [p.page_token for p in source.search_params] == [None, "PAGE-2"]
    assert quota_service.units_used_today(empty_db, NOW) >= 200


def test_uploads_are_loaded_by_playlist_not_by_search(empty_db: Session) -> None:
    # T06: canal con lista de uploads conocida → playlistItems, no search.list.
    _run(empty_db, "run-t06")
    source = FakeSource(
        upload_ids=["SYNV05"],
        videos=[synthetic_video("SYNV05", "SYNCH07")],
        channels=[synthetic_channel("SYNCH07", uploads="UU-SYN-07")],
    )
    run_discovery(  # crea el canal con su lista de uploads
        empty_db,
        FakeSource(
            hits={"x": [synthetic_hit("SYNV04", "SYNCH07")]},
            videos=[synthetic_video("SYNV04", "SYNCH07")],
            channels=[synthetic_channel("SYNCH07", uploads="UU-SYN-07")],
        ),
        _settings(),
        run_id="run-t06",
        plans=[_plan("x")],
        completed_keys=set(),
        max_search_calls=1,
        pages_per_query=1,
        now=NOW,
    )
    empty_db.commit()
    channel = empty_db.scalars(
        select(m.Channel).where(m.Channel.youtube_channel_id == "SYNCH07")
    ).one()
    loaded = load_channel_uploads(empty_db, source, _settings(), channel, run_id="run-t06", now=NOW)
    empty_db.commit()
    assert source.endpoints == ["playlistItems", "videos", "channels"]
    assert "search" not in source.endpoints
    assert [v.youtube_video_id for v in loaded] == ["SYNV05"]


def test_reingesting_the_same_results_creates_no_duplicates(empty_db: Session) -> None:
    _run(empty_db, "run-idem")
    source = FakeSource(
        hits={"q": [synthetic_hit("SYNV01", "SYNCH01")]},
        videos=[synthetic_video("SYNV01", "SYNCH01")],
        channels=[synthetic_channel("SYNCH01")],
    )
    for _ in range(2):
        run_discovery(
            empty_db,
            source,
            _settings(),
            run_id="run-idem",
            plans=[_plan("q")],
            completed_keys=set(),
            max_search_calls=2,
            pages_per_query=1,
            now=NOW,
        )
        empty_db.commit()
    assert empty_db.scalar(select(func.count()).select_from(m.Video)) == 1
    assert empty_db.scalar(select(func.count()).select_from(m.Channel)) == 1


def test_ingested_records_carry_provenance_and_retention(empty_db: Session) -> None:
    _run(empty_db, "run-prov")
    source = FakeSource(
        hits={"q": [synthetic_hit("SYNV01", "SYNCH01")]},
        videos=[synthetic_video("SYNV01", "SYNCH01")],
        channels=[synthetic_channel("SYNCH01")],
    )
    run_discovery(
        empty_db,
        source,
        _settings(),
        run_id="run-prov",
        plans=[_plan("q")],
        completed_keys=set(),
        max_search_calls=1,
        pages_per_query=1,
        now=NOW,
    )
    empty_db.commit()
    video = empty_db.scalars(select(m.Video).where(m.Video.youtube_video_id == "SYNV01")).one()
    assert video.provider == "youtube_official"
    assert video.source_data_type == "OFFICIAL"
    assert video.run_id == "run-prov"
    assert video.owner_authorized is False
    assert video.retention_deadline is not None
    assert (video.retention_deadline - NOW).days == 29
