"""vidIQ contra PostgreSQL con una fuente falsa: presupuesto, procedencia, caducidad y compuerta."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import models as m
from app.db.session import get_session_factory
from app.jobs.handlers import HandlerContext
from app.jobs.worker import process_once
from app.providers.base import ProviderAuthError, QuotaExhausted
from app.providers.vidiq_mcp import OutlierParams, OutlierVideo
from app.services import retention_service, vidiq_service
from app.services.vidiq_service import OutlierSearch

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)


def _outlier(
    video_id: str = "VID000001", channel: str = "UCchan000001", **over: Any
) -> OutlierVideo:
    base: dict[str, Any] = {
        "youtube_video_id": video_id,
        "title": f"[SINTÉTICO] {video_id}",
        "published_at": "2026-09-01T10:00:00+00:00",
        "duration_seconds": 900,
        "youtube_channel_id": channel,
        "channel_title": "Canal sintético",
        "channel_country": "US",
        "subscriber_count": 5000,
        "view_count": 120000,
        "breakout_score": 12.5,
        "views_per_hour": 80.0,
        "engagement_rate": 0.02,
        "video_type": "long",
        "trend_categories": ("video_essay",),
        "ai_labeled": None,
    }
    return OutlierVideo(**{**base, **over})


class FakeVidIQ:
    def __init__(
        self,
        items: list[OutlierVideo] | None = None,
        error: Exception | None = None,
        skipped: int = 0,
    ) -> None:
        self.items = items or []
        self.error = error
        self.skipped = skipped
        self.calls: list[OutlierParams] = []
        self.closed = False

    def outliers(self, params: OutlierParams) -> tuple[list[OutlierVideo], int]:
        self.calls.append(params)
        if self.error is not None:
            raise self.error
        return list(self.items), self.skipped

    def close(self) -> None:
        self.closed = True


def _searches(*categories: str) -> list[OutlierSearch]:
    return [OutlierSearch(OutlierParams(trend_categories=(c,))) for c in categories]


def _run(session: Session, source: FakeVidIQ, searches: list[OutlierSearch], **kw: Any) -> Any:
    settings: Settings = get_settings()
    return vidiq_service.run_outlier_discovery(
        session,
        source,
        settings,
        run_id="run-x",
        searches=searches,
        completed_keys=kw.pop("completed", set()),
        max_calls=kw.pop("max_calls", 10),
        now=NOW,
    )


def test_stores_videos_as_provider_data_with_29_day_retention(empty_db: Session) -> None:
    source = FakeVidIQ([_outlier()])
    outcome = _run(empty_db, source, _searches("video_essay"))
    empty_db.commit()
    assert outcome.outcome == "COMPLETED"
    assert (outcome.calls, outcome.credits, outcome.videos_new) == (1, 5, 1)
    video = empty_db.scalars(select(m.Video)).one()
    assert video.provider == "vidiq_api"
    assert video.source_data_type == "PROVIDER"
    assert video.owner_authorized is False
    assert video.retention_deadline == NOW + timedelta(days=29)
    assert video.language_state == "UNKNOWN"  # el filtro de idioma del proveedor no se verifica
    assert video.provider_metrics is not None
    metrics = video.provider_metrics["vidiq"]
    assert metrics["breakout_score"] == 12.5
    assert metrics["run_id"] == "run-x"
    channel = empty_db.scalars(select(m.Channel)).one()
    assert channel.subscriber_count == 5000
    assert channel.region_declared == "US"


def test_null_values_stay_null_not_zero(empty_db: Session) -> None:
    item = _outlier(
        subscriber_count=None, view_count=None, breakout_score=None, duration_seconds=None
    )
    _run(empty_db, FakeVidIQ([item]), _searches("video_essay"))
    video = empty_db.scalars(select(m.Video)).one()
    channel = empty_db.scalars(select(m.Channel)).one()
    assert video.view_count is None
    assert channel.subscriber_count is None
    assert video.provider_metrics is not None
    assert video.provider_metrics["vidiq"]["breakout_score"] is None


def test_rerun_is_idempotent_by_video_id(empty_db: Session) -> None:
    _run(empty_db, FakeVidIQ([_outlier()]), _searches("video_essay"))
    again = _run(empty_db, FakeVidIQ([_outlier(view_count=130000)]), _searches("top_x"))
    assert again.videos_new == 0
    assert again.videos_enriched == 1
    assert empty_db.scalar(select(func.count()).select_from(m.Video)) == 1


def test_existing_official_video_keeps_its_provenance(empty_db: Session) -> None:
    channel = m.Channel(
        id="c1",
        youtube_channel_id="UCchan000001",
        title_current="Oficial",
        subscriber_count=777,
        subscriber_band="B",
        language_state="UNKNOWN",
        provider="youtube_official",
        observed_at=NOW,
        source_data_type="OFFICIAL",
        owner_authorized=False,
    )
    video = m.Video(
        id="v1",
        youtube_video_id="VID000001",
        channel_id="c1",
        title="Título oficial",
        published_at=NOW,
        duration_seconds=600,
        video_type="LONG",
        video_type_evidence="x",
        language_state="CONFIRMED",
        language_confidence="HIGH",
        view_count=99,
        provider="youtube_official",
        observed_at=NOW,
        source_data_type="OFFICIAL",
    )
    empty_db.add_all([channel, video])
    empty_db.flush()
    _run(empty_db, FakeVidIQ([_outlier()]), _searches("video_essay"))
    empty_db.refresh(video)
    assert video.provider == "youtube_official"
    assert video.title == "Título oficial"
    assert video.view_count == 99
    assert video.provider_metrics is not None
    assert "vidiq" in video.provider_metrics


def test_call_budget_stops_with_partial_and_progress(empty_db: Session) -> None:
    source = FakeVidIQ([_outlier()])
    outcome = _run(empty_db, source, _searches("a_one", "b_two", "c_three"), max_calls=2)
    assert outcome.outcome == "PARTIAL"
    assert len(source.calls) == 2
    assert len(outcome.completed) == 2
    assert outcome.errors[0]["code"] == "BUDGET_CALLS"


def test_resume_skips_completed_searches(empty_db: Session) -> None:
    searches = _searches("a_one", "b_two")
    source = FakeVidIQ([_outlier()])
    outcome = _run(empty_db, source, searches, completed={searches[0].key})
    assert len(source.calls) == 1
    assert len(outcome.completed) == 2


def test_daily_credit_cap_pauses_the_run(
    empty_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDIQ_DAILY_CREDIT_LIMIT", "10")
    get_settings.cache_clear()
    source = FakeVidIQ([_outlier()])
    outcome = _run(empty_db, source, _searches("a_one", "b_two", "c_three"))
    assert outcome.outcome == "PAUSED_QUOTA"
    assert len(source.calls) == 2  # 2 x 5 = 10; la tercera no cabe
    snap = vidiq_service.snapshot(empty_db, get_settings(), NOW)
    assert snap["credits_used"] == 10
    assert snap["credits_remaining"] == 0
    monkeypatch.delenv("VIDIQ_DAILY_CREDIT_LIMIT")
    get_settings.cache_clear()


def test_remote_credit_exhaustion_pauses(empty_db: Session) -> None:
    outcome = _run(empty_db, FakeVidIQ(error=QuotaExhausted("sin créditos")), _searches("a_one"))
    assert outcome.outcome == "PAUSED_QUOTA"


def test_auth_error_fails_without_leaking(empty_db: Session) -> None:
    source = FakeVidIQ(error=ProviderAuthError("clave rechazada"))
    outcome = _run(empty_db, source, _searches("a_one"))
    assert outcome.outcome == "FAILED"
    assert outcome.errors[0]["code"] == "AUTH_ERROR"


def test_skipped_records_make_the_run_partial_and_explicit(empty_db: Session) -> None:
    outcome = _run(empty_db, FakeVidIQ([_outlier()], skipped=2), _searches("a_one"))
    assert outcome.outcome == "PARTIAL"
    assert outcome.skipped_records == 2
    assert any(e["code"] == "RECORDS_SKIPPED" for e in outcome.errors)


def test_purge_clears_vidiq_metrics_with_the_video(empty_db: Session) -> None:
    _run(empty_db, FakeVidIQ([_outlier()]), _searches("video_essay"))
    empty_db.commit()
    retention_service.purge_expired(empty_db, NOW + timedelta(days=30))
    empty_db.commit()
    video = empty_db.scalars(select(m.Video)).one()
    assert video.availability == "EXPIRED"
    assert video.provider_metrics is None
    assert video.view_count is None


# --- API y worker ------------------------------------------------------------------------------


def _approval() -> m.PolicyApproval:
    now = datetime.now(UTC)
    return m.PolicyApproval(
        id="appr-vidiq",
        provider="vidiq_api",
        capability="vidiq_api",
        scope="pruebas",
        status="ACTIVE",
        approval_ref="DOC-PRUEBA-VIDIQ",
        reviewed_by="local_owner",
        effective_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=30),
        notes="Aprobación de prueba.",
    )


@pytest.fixture
def vidiq_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("VIDIQ_API_KEY", "vidiq-TEST-NO-REAL")
    monkeypatch.setenv("COMPLIANCE_MODE", "approved_scope")
    monkeypatch.setenv("ADVANCED_ANALYTICS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("VIDIQ_API_KEY", "")
    monkeypatch.setenv("COMPLIANCE_MODE", "restricted")
    monkeypatch.setenv("ADVANCED_ANALYTICS_ENABLED", "false")
    get_settings.cache_clear()


BODY = {
    "kind": "vidiq",
    "vidiq": {"searches": [{"language": "en", "trend_categories": ["video_essay"]}]},
}


def _ctx(source: FakeVidIQ) -> HandlerContext:
    return HandlerContext(
        settings=get_settings(),
        make_source=lambda: (_ for _ in ()).throw(AssertionError("YouTube no debe usarse")),
        make_vidiq=lambda: source,
    )


def test_api_requires_a_key(client: TestClient) -> None:
    response = client.post("/api/v1/research-runs", json=BODY)
    assert response.status_code == 409
    assert response.json()["code"] == "PROVIDER_NOT_CONFIGURED"


def test_api_blocked_without_approval(client: TestClient, vidiq_env: None) -> None:
    response = client.post("/api/v1/research-runs", json=BODY)
    assert response.status_code == 403
    assert response.json()["code"] == "POLICY_RESTRICTED"


def test_api_rejects_unsafe_input(client: TestClient, vidiq_env: None, seeded_db: Session) -> None:
    seeded_db.add(_approval())
    seeded_db.commit()
    bad = {
        "kind": "vidiq",
        "vidiq": {"searches": [{"language": "en", "trend_categories": ["x; DROP TABLE videos"]}]},
    }
    assert client.post("/api/v1/research-runs", json=bad).status_code == 422
    assert client.post("/api/v1/research-runs", json={"kind": "vidiq"}).status_code == 422


def test_end_to_end_run_through_the_worker(
    client: TestClient, vidiq_env: None, seeded_db: Session
) -> None:
    seeded_db.add(_approval())
    seeded_db.commit()
    response = client.post("/api/v1/research-runs", json=BODY)
    assert response.status_code == 202
    run_id = response.json()["id"]

    source = FakeVidIQ([_outlier("E2EVID001", "UCe2e0000001")])
    assert process_once(get_session_factory(), _ctx(source)) is True
    run = client.get(f"/api/v1/research-runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    assert run["coverage"]["credits"] == 5
    assert run["coverage"]["videos_new"] == 1
    assert source.closed is True
    assert client.get("/api/v1/usage/vidiq").json()["credits_used"] == 5
    with get_session_factory()() as session:
        stored = session.scalars(
            select(m.Video).where(m.Video.youtube_video_id == "E2EVID001")
        ).one()
        assert stored.provider == "vidiq_api"


def test_worker_refuses_when_gate_closes_after_enqueue(
    client: TestClient, vidiq_env: None, seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded_db.add(_approval())
    seeded_db.commit()
    run_id = client.post("/api/v1/research-runs", json=BODY).json()["id"]
    monkeypatch.setenv("COMPLIANCE_MODE", "restricted")
    get_settings.cache_clear()
    source = FakeVidIQ([_outlier()])
    process_once(get_session_factory(), _ctx(source))
    run = client.get(f"/api/v1/research-runs/{run_id}").json()
    assert run["status"] == "FAILED"
    assert source.calls == []
    assert run["errors"][0]["code"] == "POLICY_RESTRICTED"


def test_provider_status_reflects_key_without_exposing_it(
    client: TestClient, vidiq_env: None
) -> None:
    providers = {p["id"]: p for p in client.get("/api/v1/providers").json()}
    assert providers["vidiq_api"]["status"] == "CONFIGURED"
    assert "TEST-NO-REAL" not in str(providers)
