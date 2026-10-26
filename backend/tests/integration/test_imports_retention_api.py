"""Importación, purga, cuota por día y API de corridas M1 (sin red)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db import models as m
from app.jobs import worker
from app.jobs.handlers import HandlerContext
from app.services import quota_service, retention_service
from app.services.import_service import import_rows
from tests.fakes import FakeSource, synthetic_channel, synthetic_hit, synthetic_video

NOW = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)


def _row(video_id: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "youtube_video_id": video_id,
        "youtube_channel_id": "SYNCH01",
        "channel_title": "Canal Sintético Alfa",
        "title": f"[SINTÉTICO] {video_id}",
        "published_at": "2026-10-01T12:00:00+00:00",
        "duration_seconds": 720,
        "default_language": None,
        "default_audio_language": "pt",
        "view_count": 4000,
        "subscriber_count": 1200,
        "live_broadcast": "none",
    }
    row.update(overrides)
    return row


def _settings() -> Settings:
    return get_settings()


# --- importación -----------------------------------------------------------------------------


def test_partial_import_accepts_valid_rows_and_reports_bad_ones(empty_db: Session) -> None:
    rows = [
        _row("SYNV21"),
        _row("bad id!"),  # id con caracteres no válidos
        _row("SYNV22", published_at="2026-10-01T12:00:00"),  # sin zona horaria
        _row("SYNV23", duration_seconds=-5),
    ]
    summary = import_rows(
        empty_db,
        _settings(),
        provider="vidiq_import",
        idempotency_key="lote-1",
        license_confirmed=True,
        source_schema_version="1",
        rows=rows,
        now=NOW,
    )
    empty_db.commit()
    assert summary["received"] == 4
    assert summary["accepted"] == 1
    assert summary["rejected"] == 3
    fields = {(e["row"], e["field"]) for e in summary["errors"]}
    assert (2, "youtube_video_id") in fields
    assert (3, "published_at") in fields
    assert (4, "duration_seconds") in fields
    assert empty_db.scalar(select(m.Video).where(m.Video.youtube_video_id == "SYNV21")) is not None


def test_reimporting_same_key_is_idempotent(empty_db: Session) -> None:
    # T21 (importación): misma clave → no vuelve a aplicar nada.
    rows = [_row("SYNV31"), _row("SYNV32")]
    first = import_rows(
        empty_db,
        _settings(),
        provider="vidiq_import",
        idempotency_key="lote-2",
        license_confirmed=True,
        source_schema_version="1",
        rows=rows,
        now=NOW,
    )
    empty_db.commit()
    second = import_rows(
        empty_db,
        _settings(),
        provider="vidiq_import",
        idempotency_key="lote-2",
        license_confirmed=True,
        source_schema_version="1",
        rows=rows,
        now=NOW,
    )
    empty_db.commit()
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert empty_db.scalar(select(m.Video).where(m.Video.youtube_video_id == "SYNV31")) is not None


def test_import_without_license_confirmation_is_refused(empty_db: Session) -> None:
    import pytest

    from app.core.errors import ProblemError

    with pytest.raises(ProblemError) as info:
        import_rows(
            empty_db,
            _settings(),
            provider="vidiq_import",
            idempotency_key="x",
            license_confirmed=False,
            source_schema_version="1",
            rows=[_row("SYNV41")],
        )
    assert info.value.code == "LICENSE_NOT_CONFIRMED"


def test_imported_rows_are_marked_provider_and_expire(empty_db: Session) -> None:
    import_rows(
        empty_db,
        _settings(),
        provider="vidiq_import",
        idempotency_key="lote-3",
        license_confirmed=True,
        source_schema_version="1",
        rows=[_row("SYNV51")],
        now=NOW,
    )
    empty_db.commit()
    video = empty_db.scalars(select(m.Video).where(m.Video.youtube_video_id == "SYNV51")).one()
    assert video.source_data_type == "PROVIDER"
    assert video.provider == "vidiq_import"
    assert video.owner_authorized is False
    assert video.retention_deadline is not None
    assert (video.retention_deadline - NOW).days == 29


def test_csv_with_formula_text_is_stored_as_plain_text(empty_db: Session) -> None:
    header = (
        "youtube_video_id,youtube_channel_id,channel_title,title,published_at,duration_seconds,"
        "default_language,default_audio_language,view_count,subscriber_count,live_broadcast"
    )
    line = 'SYNV61,SYNCH01,Canal Sintético Alfa,=HYPERLINK("http://x"),2026-10-01T12:00:00+00:00,720,,pt,10,1200,none'
    summary = import_rows(
        empty_db,
        _settings(),
        provider="manual_import",
        idempotency_key="csv-1",
        license_confirmed=True,
        source_schema_version="1",
        csv_text=f"{header}\n{line}\n",
        now=NOW,
    )
    empty_db.commit()
    assert summary["accepted"] == 1
    video = empty_db.scalars(select(m.Video).where(m.Video.youtube_video_id == "SYNV61")).one()
    assert video.title.startswith(
        "=HYPERLINK"
    )  # se guarda como texto; la exportación lo neutralizará (T20)


def test_csv_missing_required_columns_is_rejected(empty_db: Session) -> None:
    import pytest

    from app.core.errors import ProblemError

    with pytest.raises(ProblemError) as info:
        import_rows(
            empty_db,
            _settings(),
            provider="manual_import",
            idempotency_key="csv-2",
            license_confirmed=True,
            source_schema_version="1",
            csv_text="youtube_video_id\nSYNV71\n",
        )
    assert info.value.code == "CSV_COLUMNS_MISSING"


# --- purga de retención (T16) -----------------------------------------------------------------


def _seed_expiring(session: Session) -> None:
    channel = m.Channel(
        id="ch-exp",
        youtube_channel_id="SYNCHX",
        title_current="Canal Sintético X",
        subscriber_count=900,
        subscriber_band="[0,1000)",
        language_state="UNKNOWN",
        provider="youtube_official",
        observed_at=NOW - timedelta(days=40),
        source_data_type="OFFICIAL",
        owner_authorized=False,
        retention_deadline=NOW - timedelta(days=11),
    )
    video = m.Video(
        id="v-exp",
        youtube_video_id="SYNVX",
        channel_id="ch-exp",
        title="[SINTÉTICO] viejo",
        published_at=NOW - timedelta(days=50),
        duration_seconds=720,
        video_type="LONG",
        video_type_evidence="x",
        language_state="pt",
        language_confidence="HIGH",
        view_count=5000,
        url="https://www.youtube.com/watch?v=SYNVX",
        provider="youtube_official",
        observed_at=NOW - timedelta(days=40),
        source_data_type="OFFICIAL",
        availability="AVAILABLE",
        owner_authorized=False,
        retention_deadline=NOW - timedelta(days=11),
    )
    fresh = m.Video(
        id="v-new",
        youtube_video_id="SYNVY",
        channel_id="ch-exp",
        title="[SINTÉTICO] reciente",
        published_at=NOW - timedelta(days=2),
        duration_seconds=720,
        video_type="LONG",
        video_type_evidence="x",
        language_state="pt",
        language_confidence="HIGH",
        view_count=300,
        url="https://www.youtube.com/watch?v=SYNVY",
        provider="youtube_official",
        observed_at=NOW,
        source_data_type="OFFICIAL",
        availability="AVAILABLE",
        owner_authorized=False,
        retention_deadline=NOW + timedelta(days=27),
    )
    session.add_all([channel, video, fresh])
    session.commit()


def test_purge_expires_old_third_party_data_without_zeros(empty_db: Session) -> None:
    _seed_expiring(empty_db)
    counts = retention_service.purge_expired(empty_db, NOW)
    empty_db.commit()
    assert counts == {
        "videos_expired": 1,
        "channels_expired": 1,
        "demand_observations_expired": 0,
    }
    expired = empty_db.get(m.Video, "v-exp")
    assert expired is not None
    assert expired.availability == "EXPIRED"
    assert expired.view_count is None  # NULL, nunca 0
    assert expired.url is None
    assert expired.title == retention_service.EXPIRED_TITLE
    channel = empty_db.get(m.Channel, "ch-exp")
    assert channel is not None and channel.subscriber_count is None


def test_purge_leaves_fresh_and_authorized_data_alone(empty_db: Session) -> None:
    _seed_expiring(empty_db)
    fresh = empty_db.get(m.Video, "v-new")
    assert fresh is not None
    fresh.owner_authorized = True
    empty_db.commit()
    retention_service.purge_expired(empty_db, NOW)
    empty_db.commit()
    still = empty_db.get(m.Video, "v-new")
    assert still is not None and still.availability == "AVAILABLE" and still.view_count == 300


def test_purge_is_idempotent(empty_db: Session) -> None:
    _seed_expiring(empty_db)
    retention_service.purge_expired(empty_db, NOW)
    empty_db.commit()
    again = retention_service.purge_expired(empty_db, NOW)
    assert again == {
        "videos_expired": 0,
        "channels_expired": 0,
        "demand_observations_expired": 0,
    }


# --- cuota por día de Pacific Time ------------------------------------------------------------


def test_quota_day_starts_at_pacific_midnight() -> None:
    # 2026-10-24 06:00 UTC = 23:00 PT del 23 → el día de cuota aún es el 23.
    before_reset = datetime(2026, 10, 24, 6, 0, tzinfo=UTC)
    after_reset = datetime(2026, 10, 24, 8, 0, tzinfo=UTC)  # 01:00 PT del 24
    assert quota_service.quota_day_start(before_reset) == datetime(2026, 10, 23, 7, 0, tzinfo=UTC)
    assert quota_service.quota_day_start(after_reset) == datetime(2026, 10, 24, 7, 0, tzinfo=UTC)


def test_units_used_counts_only_current_quota_day(empty_db: Session) -> None:
    empty_db.add_all(
        [
            m.ProviderUsage(
                id="u1",
                run_id=None,
                provider="youtube_official",
                endpoint="search",
                quota_bucket="youtube_units",
                units=100,
                started_at=datetime(2026, 10, 23, 12, tzinfo=UTC),
                status="RESERVED",
            ),
            m.ProviderUsage(
                id="u2",
                run_id=None,
                provider="youtube_official",
                endpoint="videos",
                quota_bucket="youtube_units",
                units=7,
                started_at=datetime(2026, 10, 24, 9, tzinfo=UTC),
                status="RESERVED",
            ),
        ]
    )
    empty_db.commit()
    assert quota_service.units_used_today(empty_db, datetime(2026, 10, 24, 9, 30, tzinfo=UTC)) == 7


# --- API de corridas M1 -----------------------------------------------------------------------


def _discovery_body() -> dict[str, Any]:
    return {
        "kind": "discovery",
        "payload": {
            "queries": [{"language": "es", "query": "historia con mapas", "window": "0-7"}],
            "max_search_calls": 2,
            "pages_per_query": 1,
        },
    }


def test_discovery_without_key_is_refused_before_queueing(client: TestClient) -> None:
    response = client.post("/api/v1/research-runs", json=_discovery_body())
    assert response.status_code == 409
    assert response.json()["code"] == "PROVIDER_NOT_CONFIGURED"


def test_discovery_payload_is_validated(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "TEST-KEY")
    get_settings.cache_clear()
    try:
        bad = _discovery_body()
        bad["payload"]["max_search_calls"] = 500
        assert client.post("/api/v1/research-runs", json=bad).status_code == 422
        bad_window = _discovery_body()
        bad_window["payload"]["queries"][0]["window"] = "1-2"
        assert client.post("/api/v1/research-runs", json=bad_window).status_code == 422
    finally:
        monkeypatch.setenv("YOUTUBE_API_KEY", "")
        get_settings.cache_clear()


def test_discovery_run_executes_with_fake_source_and_reports_coverage(
    client: TestClient, monkeypatch: Any, seeded_db: Session
) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "TEST-KEY")
    get_settings.cache_clear()
    try:
        run_id = client.post("/api/v1/research-runs", json=_discovery_body()).json()["id"]
        source = FakeSource(
            hits={"historia con mapas": [synthetic_hit("SYNV81", "SYNCH81")]},
            videos=[synthetic_video("SYNV81", "SYNCH81")],
            channels=[synthetic_channel("SYNCH81")],
        )
        ctx = HandlerContext(settings=get_settings(), make_source=lambda: source)
        factory: sessionmaker[Session] = worker.get_session_factory()
        assert worker.process_once(factory, ctx) is True
        run = client.get(f"/api/v1/research-runs/{run_id}").json()
        assert run["status"] == "COMPLETED"
        assert run["coverage"]["searches"] == 1
        assert run["coverage"]["per_language"]["es"]["videos"] == 1
        assert any(e["event_type"] == "RUN_REQUESTED" for e in run["events"])
        assert source.closed is True
    finally:
        monkeypatch.setenv("YOUTUBE_API_KEY", "")
        get_settings.cache_clear()


def test_quota_pause_then_resume_completes_remaining_work(
    client: TestClient, monkeypatch: Any, seeded_db: Session
) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "TEST-KEY")
    monkeypatch.setenv("YOUTUBE_DAILY_UNITS_LIMIT", "150")
    get_settings.cache_clear()
    try:
        body = {
            "kind": "discovery",
            "payload": {
                "queries": [
                    {"language": "es", "query": "uno", "window": "0-7"},
                    {"language": "pt", "query": "dois", "window": "0-7"},
                ],
                "max_search_calls": 5,
                "pages_per_query": 1,
            },
        }
        run_id = client.post("/api/v1/research-runs", json=body).json()["id"]
        factory = worker.get_session_factory()
        source = FakeSource()
        ctx = HandlerContext(settings=get_settings(), make_source=lambda: source)
        worker.process_once(factory, ctx)
        paused = client.get(f"/api/v1/research-runs/{run_id}").json()
        assert paused["status"] == "PAUSED_QUOTA"
        assert paused["coverage"]["queries_completed"] == 1

        # Al día siguiente (presupuesto reiniciado): se reanuda y solo falta la segunda consulta.
        with factory() as session, session.begin():
            session.execute(m.ProviderUsage.__table__.delete())
        assert client.post(f"/api/v1/research-runs/{run_id}/resume").status_code == 202
        worker.process_once(factory, ctx)
        resumed = client.get(f"/api/v1/research-runs/{run_id}").json()
        assert resumed["status"] == "COMPLETED"
        assert resumed["coverage"]["queries_completed"] == 2
        assert [p.query for p in source.search_params] == ["uno", "dois"]
    finally:
        monkeypatch.setenv("YOUTUBE_API_KEY", "")
        monkeypatch.delenv("YOUTUBE_DAILY_UNITS_LIMIT", raising=False)
        get_settings.cache_clear()


def test_resume_is_refused_for_runs_not_paused(client: TestClient) -> None:
    run_id = client.post("/api/v1/research-runs", json={"kind": "purge"}).json()["id"]
    response = client.post(f"/api/v1/research-runs/{run_id}/resume")
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_RESUMABLE"


def test_purge_run_completes_through_worker(client: TestClient, seeded_db: Session) -> None:
    run_id = client.post("/api/v1/research-runs", json={"kind": "purge"}).json()["id"]
    assert worker.process_once(worker.get_session_factory()) is True
    run = client.get(f"/api/v1/research-runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    assert "videos_expired" in run["coverage"]


def test_usage_endpoint_reports_budget(client: TestClient) -> None:
    body = client.get("/api/v1/usage").json()
    assert body["units_limit_hard"] == 10_000
    assert body["units_budget_soft"] == 9_000
    assert body["units_used"] == 0


def test_channel_detail_and_video_provenance(client: TestClient) -> None:
    channel = client.get("/api/v1/channels/SYNCH04").json()
    assert channel["subscriber_count"] == 0
    assert channel["video_count"] >= 1
    video = client.get(
        "/api/v1/videos", params={"source_data_type": "SYNTHETIC", "page_size": 1}
    ).json()
    item = video["items"][0]
    assert {"owner_authorized", "retention_deadline", "last_refreshed_at"} <= set(item)


def test_unknown_channel_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/channels/NO-EXISTE").status_code == 404
