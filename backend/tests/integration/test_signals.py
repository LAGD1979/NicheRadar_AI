"""Demanda en español y persistencia temporal con proveedores simulados (D-63)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models as m
from app.db.session import get_session_factory
from app.jobs.handlers import HandlerContext
from app.jobs.worker import process_once
from app.providers.base import ProviderAuthError, QuotaExhausted
from app.providers.hasdata import RelatedQuery, TrendPoint
from app.providers.vidiq_mcp import HistoryPoint, KeywordMetrics
from app.services import demand_service, persistence_service, retention_service
from app.services import spanish_service as svc

OPP = "syn-opp-01"
NOW = datetime.now(UTC)
PUBLISHED = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)  # fecha de publicación de los videos de prueba


class FakeTrends:
    def __init__(self, values: list[int | None] | None = None, error: Exception | None = None):
        self.values = values if values is not None else [40] * 52
        self.error = error
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def interest_over_time(self, query: str, *, geo: str = "", **_: Any) -> list[TrendPoint]:
        self.calls.append((query, geo))
        if self.error:
            raise self.error
        return [
            TrendPoint(NOW - timedelta(weeks=len(self.values) - i), value, False)
            for i, value in enumerate(self.values)
        ]

    def related_queries(self, query: str, **_: Any) -> list[RelatedQuery]:
        return [RelatedQuery("consulta relacionada", "top", 100)]

    def close(self) -> None:
        self.closed = True


class FakeKeywords:
    def __init__(self, monthly: int | None = 22_318, growth: float | None = 55.9):
        self.monthly = monthly
        self.growth = growth
        self.calls: list[str] = []

    def keyword_research(self, keyword: str, *, country: str | None = None) -> KeywordMetrics:
        self.calls.append(keyword)
        return KeywordMetrics(keyword, self.monthly, 64.9, 31.7, self.growth, None, "2026-10-25")

    def close(self) -> None:
        return None


def _observe(session: Session, **over: Any) -> demand_service.DemandOutcome:
    args: dict[str, Any] = {
        "opportunity_id": OPP,
        "keywords": ["video ensayo"],
        "geo": None,
        "sources": ["trends", "vidiq"],
        "include_related": False,
        "trends": FakeTrends(),
        "vidiq": FakeKeywords(),
        "run_id": None,
        "completed_keys": set(),
        "now": NOW,
    }
    return demand_service.observe(session, get_settings(), **{**args, **over})


def _spanish(session: Session) -> dict[str, Any]:
    evaluation = session.scalars(
        select(m.Evaluation)
        .where(m.Evaluation.opportunity_id == OPP)
        .order_by(m.Evaluation.evaluation_version.desc())
    ).first()
    assert evaluation is not None
    return evaluation.spanish_json


# --- servicio -----------------------------------------------------------------------------------


def test_two_independent_sources_make_demand_observed(seeded_db: Session) -> None:
    outcome = _observe(seeded_db)
    seeded_db.commit()
    assert outcome.outcome == "COMPLETED"
    assert (outcome.hasdata_calls, outcome.vidiq_credits, outcome.observations) == (1, 5, 2)
    spanish = _spanish(seeded_db)
    assert spanish["demand_signals"]["independent_signals"] == 2
    assert spanish["spanish_demand_state"] == "OBSERVED"
    rows = seeded_db.scalars(select(m.DemandObservation)).all()
    assert {r.family for r in rows} == {"google_trends", "vidiq_keywords"}
    assert all(r.retention_deadline == NOW + timedelta(days=29) for r in rows)
    assert all(r.source_data_type == "PROVIDER" for r in rows)


def test_one_source_is_only_indicative(seeded_db: Session) -> None:
    _observe(seeded_db, sources=["trends"], vidiq=None)
    assert _spanish(seeded_db)["spanish_demand_state"] == "INDICATIVE"


def test_several_keywords_from_one_source_still_count_once(seeded_db: Session) -> None:
    _observe(
        seeded_db, keywords=["uno uno", "dos dos", "tres tres"], sources=["vidiq"], trends=None
    )
    spanish = _spanish(seeded_db)
    assert spanish["demand_signals"]["independent_signals"] == 1
    assert spanish["spanish_demand_state"] == "INDICATIVE"


def test_missing_data_is_unknown_and_never_not_observed(seeded_db: Session) -> None:
    _observe(
        seeded_db,
        trends=FakeTrends([None] * 52),
        vidiq=FakeKeywords(monthly=None, growth=None),
    )
    spanish = _spanish(seeded_db)
    assert spanish["demand_signals"]["independent_signals"] == 0
    assert spanish["spanish_demand_state"] == "UNPROVEN"
    assert {r.state for r in seeded_db.scalars(select(m.DemandObservation))} == {"UNKNOWN"}


def test_low_demand_is_observed_but_does_not_count(seeded_db: Session) -> None:
    _observe(seeded_db, trends=FakeTrends([2] * 52), vidiq=FakeKeywords(monthly=120))
    spanish = _spanish(seeded_db)
    assert spanish["demand_signals"]["independent_signals"] == 0
    assert spanish["demand_signals"]["family_states"]["google_trends"] == "NOT_PRESENT"


def test_related_queries_cost_an_extra_call_and_are_stored(seeded_db: Session) -> None:
    outcome = _observe(seeded_db, sources=["trends"], vidiq=None, include_related=True)
    assert outcome.hasdata_calls == 2
    row = seeded_db.scalars(select(m.DemandObservation)).one()
    assert row.result_json["related"][0]["query"] == "consulta relacionada"
    assert row.result_json["series"][0] == 40


def test_the_latest_observation_replaces_the_previous_one(seeded_db: Session) -> None:
    _observe(seeded_db, sources=["trends"], vidiq=None, trends=FakeTrends([40] * 52))
    _observe(
        seeded_db,
        sources=["trends"],
        vidiq=None,
        trends=FakeTrends([2] * 52),
        now=NOW + timedelta(minutes=5),
    )
    spanish = _spanish(seeded_db)
    assert spanish["demand_signals"]["family_states"]["google_trends"] == "NOT_PRESENT"
    assert seeded_db.scalar(select(func.count()).select_from(m.DemandObservation)) == 2


def test_daily_hasdata_limit_pauses_the_run(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HASDATA_DAILY_CALL_LIMIT", "2")
    get_settings.cache_clear()
    trends = FakeTrends()
    outcome = _observe(
        seeded_db,
        keywords=["uno uno", "dos dos", "tres tres"],
        sources=["trends"],
        vidiq=None,
        trends=trends,
    )
    assert outcome.outcome == "PAUSED_QUOTA"
    assert len(trends.calls) == 2
    snapshot = demand_service.hasdata_snapshot(seeded_db, get_settings(), NOW)
    assert snapshot["calls_used"] == 2
    assert snapshot["calls_remaining"] == 0
    monkeypatch.delenv("HASDATA_DAILY_CALL_LIMIT")
    get_settings.cache_clear()


def test_provider_errors_are_reported_without_inventing_data(seeded_db: Session) -> None:
    exhausted = _observe(
        seeded_db,
        sources=["trends"],
        vidiq=None,
        trends=FakeTrends(error=QuotaExhausted("sin créditos")),
    )
    assert exhausted.outcome == "PAUSED_QUOTA"
    auth = _observe(
        seeded_db,
        sources=["trends"],
        vidiq=None,
        trends=FakeTrends(error=ProviderAuthError("clave rechazada")),
    )
    assert auth.outcome == "FAILED"
    assert seeded_db.scalar(select(func.count()).select_from(m.DemandObservation)) == 0


def test_resume_skips_completed_pairs(seeded_db: Session) -> None:
    trends = FakeTrends()
    done = {"trends:video ensayo:"}
    outcome = _observe(
        seeded_db, sources=["trends"], vidiq=None, trends=trends, completed_keys=done
    )
    assert trends.calls == []
    assert outcome.observations == 0


def test_expired_observations_stop_counting(seeded_db: Session) -> None:
    _observe(seeded_db)
    seeded_db.commit()
    retention_service.purge_expired(seeded_db, NOW + timedelta(days=40))
    seeded_db.commit()
    rows = seeded_db.scalars(select(m.DemandObservation)).all()
    assert {r.availability for r in rows} == {"EXPIRED"}
    assert all(r.result_json == {} for r in rows)
    svc.record_assessment(seeded_db, OPP, None, NOW + timedelta(days=40))
    assert _spanish(seeded_db)["demand_signals"]["independent_signals"] == 0


def test_exact_competitors_consumption_is_the_third_family(
    seeded_db: Session, open_policy: Callable[..., None]
) -> None:
    open_policy("derived_metrics")
    from tests.integration.test_m4_dimensions import _seed_competitors

    _seed_competitors(seeded_db, [(120_000, 8_000), (90_000, 12_000), (70_000, 9_000)])
    svc.record_assessment(seeded_db, OPP, None, NOW)
    demand = _spanish(seeded_db)["demand_signals"]
    assert demand["family_states"]["youtube_consumption"] == "PRESENT"
    assert demand["independent_signals"] == 1
    _observe(seeded_db, sources=["vidiq"], trends=None)
    assert _spanish(seeded_db)["spanish_demand_state"] == "OBSERVED"  # vidIQ + consumo


def test_consumption_is_restricted_without_the_derived_metrics_gate(seeded_db: Session) -> None:
    from tests.integration.test_m4_dimensions import _seed_competitors

    _seed_competitors(seeded_db, [(120_000, 8_000), (90_000, 12_000), (70_000, 9_000)])
    svc.record_assessment(seeded_db, OPP, None, NOW)
    states = _spanish(seeded_db)["demand_signals"]["family_states"]
    assert states["youtube_consumption"] == "UNKNOWN"


# --- persistencia ------------------------------------------------------------------------------


class FakeHistory:
    def __init__(self, gains: list[int] | None = None) -> None:
        self.gains = gains if gains is not None else [1000] * 30
        self.calls: list[str] = []

    def video_history(self, video_id: str) -> list[HistoryPoint]:
        self.calls.append(video_id)
        start = PUBLISHED + timedelta(hours=1)  # el historial empieza con la publicación
        total = 0
        points = [HistoryPoint(start, 0, 0.0)]
        for day, gain in enumerate(self.gains, start=1):
            total += gain
            points.append(HistoryPoint(start + timedelta(days=day), total, 1.0))
        return points

    def close(self) -> None:
        return None


def _annotated_videos(client: TestClient, session: Session, count: int = 4) -> str:
    from app.providers.vidiq_mcp import OutlierParams
    from app.services import vidiq_service
    from app.services.vidiq_service import OutlierSearch
    from tests.integration.test_vidiq import _outlier  # reutiliza el generador de videos

    class _Src:
        def outliers(self, params: OutlierParams) -> tuple[list[Any], int]:
            return [_outlier(f"PERSV{i:05d}", f"UCpers{i:08d}") for i in range(count)], 0

    vidiq_service.run_outlier_discovery(
        session,
        _Src(),
        get_settings(),
        run_id="r",
        searches=[OutlierSearch(OutlierParams())],
        completed_keys=set(),
        max_calls=1,
        now=NOW,
    )
    session.commit()
    niche = client.post(
        "/api/v1/taxonomy/niches",
        json={"name": "Nicho persistencia", "definition": "Definición suficientemente larga."},
    ).json()["id"]
    fmt = client.post(
        "/api/v1/taxonomy/formats",
        json={
            "name": "Formato persistencia",
            "story_structure": "Estructura suficientemente larga.",
        },
    ).json()["id"]
    opp_id = ""
    items = client.get("/api/v1/videos", params={"provider": "vidiq_api", "page_size": 50}).json()
    for video in items["items"]:
        if video["youtube_video_id"].startswith("PERSV"):
            response = client.post(
                f"/api/v1/videos/{video['id']}/annotations",
                json={
                    "niche_id": niche,
                    "format_id": fmt,
                    "same_format_confidence": "HIGH",
                    "rationale": "Mismo formato según la categoría del proveedor.",
                },
            )
            opp_id = response.json()["opportunity_id"]
    return opp_id


def test_persistence_is_measured_per_video_and_aggregated(
    client: TestClient, seeded_db: Session
) -> None:
    opp_id = _annotated_videos(client, seeded_db)
    source = FakeHistory()
    outcome = persistence_service.measure(
        seeded_db, get_settings(), source, opportunity_id=opp_id, max_calls=10, run_id=None, now=NOW
    )
    seeded_db.commit()
    assert (outcome.calls, outcome.credits, outcome.videos_measured) == (4, 20, 4)
    assert outcome.aggregate["state"] == "OBSERVED"
    assert outcome.aggregate["ratio"] == 1.0
    evaluation = seeded_db.scalars(
        select(m.Evaluation)
        .where(m.Evaluation.opportunity_id == opp_id)
        .order_by(m.Evaluation.evaluation_version.desc())
    ).first()
    assert evaluation is not None
    assert evaluation.international_json["temporal_resilience"]["ratio"] == 1.0
    video = seeded_db.scalars(select(m.Video).where(m.Video.youtube_video_id == "PERSV00000")).one()
    assert video.provider_metrics is not None
    assert video.provider_metrics["vidiq_history"]["state"] == "OBSERVED"
    assert "vidiq" in video.provider_metrics  # las métricas anteriores se conservan


def test_recent_measurements_are_not_repeated_and_budget_is_respected(
    client: TestClient, seeded_db: Session
) -> None:
    opp_id = _annotated_videos(client, seeded_db)
    source = FakeHistory()
    first = persistence_service.measure(
        seeded_db, get_settings(), source, opportunity_id=opp_id, max_calls=2, run_id=None, now=NOW
    )
    assert first.outcome == "PARTIAL"
    assert first.calls == 2
    second = persistence_service.measure(
        seeded_db,
        get_settings(),
        source,
        opportunity_id=opp_id,
        max_calls=10,
        run_id=None,
        now=NOW + timedelta(hours=1),
    )
    assert second.videos_skipped_fresh == 2
    assert second.calls == 2
    assert len(source.calls) == 4


def test_short_histories_do_not_score(client: TestClient, seeded_db: Session) -> None:
    opp_id = _annotated_videos(client, seeded_db)
    outcome = persistence_service.measure(
        seeded_db,
        get_settings(),
        FakeHistory([1000] * 5),
        opportunity_id=opp_id,
        max_calls=10,
        run_id=None,
        now=NOW,
    )
    assert outcome.aggregate["ratio"] is None
    assert outcome.aggregate["state"] == "INSUFFICIENT_VIDEOS"


def test_replication_refresh_keeps_the_temporal_resilience(
    client: TestClient, seeded_db: Session, open_policy: Callable[..., None]
) -> None:
    open_policy("derived_metrics")
    opp_id = _annotated_videos(client, seeded_db)
    persistence_service.measure(
        seeded_db,
        get_settings(),
        FakeHistory(),
        opportunity_id=opp_id,
        max_calls=10,
        run_id=None,
        now=NOW,
    )
    seeded_db.commit()
    assert client.post(f"/api/v1/opportunities/{opp_id}/replication/refresh").status_code == 200
    intl = client.get(f"/api/v1/opportunities/{opp_id}").json()["evaluation"]["international"]
    assert intl["replication_state"]
    assert intl["temporal_resilience"]["ratio"] == 1.0


def test_scores_use_temporal_resilience_and_demand(client: TestClient, seeded_db: Session) -> None:
    from app.services import scoring_service

    opp_id = _annotated_videos(client, seeded_db)
    persistence_service.measure(
        seeded_db,
        get_settings(),
        FakeHistory(),
        opportunity_id=opp_id,
        max_calls=10,
        run_id=None,
        now=NOW,
    )
    evaluation = seeded_db.scalars(
        select(m.Evaluation)
        .where(m.Evaluation.opportunity_id == opp_id)
        .order_by(m.Evaluation.evaluation_version.desc())
    ).first()
    assert evaluation is not None
    scores = scoring_service.compute_for_evaluation(evaluation, (None, None))
    assert scores["dimensions"]["international"]["resiliencia_temporal"] == 1.0


# --- API y worker ------------------------------------------------------------------------------


BODY = {"keywords": ["video ensayo"], "geo": "MX", "sources": ["trends", "vidiq"]}


@pytest.fixture
def providers_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("HASDATA_API_KEY", "hasdata-TEST-NO-REAL")
    monkeypatch.setenv("VIDIQ_API_KEY", "vidiq-TEST-NO-REAL")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("HASDATA_API_KEY", "")
    monkeypatch.setenv("VIDIQ_API_KEY", "")
    get_settings.cache_clear()


def test_demand_endpoint_requires_keys_then_the_gate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"/api/v1/opportunities/{OPP}/demand"
    assert client.post(url, json=BODY).json()["code"] == "PROVIDER_NOT_CONFIGURED"
    monkeypatch.setenv("HASDATA_API_KEY", "hasdata-TEST-NO-REAL")
    monkeypatch.setenv("VIDIQ_API_KEY", "vidiq-TEST-NO-REAL")
    get_settings.cache_clear()
    blocked = client.post(url, json=BODY)
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "POLICY_RESTRICTED"
    monkeypatch.setenv("HASDATA_API_KEY", "")
    monkeypatch.setenv("VIDIQ_API_KEY", "")
    get_settings.cache_clear()


def test_demand_endpoint_rejects_bad_input_and_unknown_opportunities(
    client: TestClient, providers_on: None, open_policy: Callable[..., None]
) -> None:
    open_policy("google_trends", "vidiq_api")
    url = f"/api/v1/opportunities/{OPP}/demand"
    assert client.post(url, json={**BODY, "keywords": []}).status_code == 422
    assert client.post(url, json={**BODY, "keywords": ["a"]}).status_code == 422
    assert client.post(url, json={**BODY, "keywords": ["uno\x07dos"]}).status_code == 422
    assert client.post(url, json={**BODY, "keywords": ["a b"] * 9}).status_code == 422
    assert client.post(url, json={**BODY, "geo": "mx"}).status_code == 422
    assert client.post(url, json={**BODY, "sources": ["otra"]}).status_code == 422
    assert client.post("/api/v1/opportunities/no-existe/demand", json=BODY).status_code == 404


def test_end_to_end_demand_run_through_the_worker(
    client: TestClient, providers_on: None, open_policy: Callable[..., None]
) -> None:
    open_policy("google_trends", "vidiq_api")
    response = client.post(f"/api/v1/opportunities/{OPP}/demand", json=BODY)
    assert response.status_code == 202
    assert response.json()["budget"] == {
        "hasdata_calls_estimate": 1,
        "hasdata_credits_estimate": 10,
        "vidiq_credits_estimate": 5,
    }
    run_id = response.json()["id"]
    trends, keywords = FakeTrends(), FakeKeywords()
    ctx = HandlerContext(
        settings=get_settings(),
        make_source=lambda: (_ for _ in ()).throw(AssertionError("YouTube no debe usarse")),
        make_vidiq=lambda: keywords,
        make_hasdata=lambda: trends,
    )
    assert process_once(get_session_factory(), ctx) is True
    run = client.get(f"/api/v1/research-runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    assert run["coverage"]["observations"] == 2
    assert trends.closed is True
    assert trends.calls == [("video ensayo", "MX")]
    demand = client.get(f"/api/v1/opportunities/{OPP}/demand").json()
    assert demand["family_states"]["google_trends"] == "PRESENT"
    assert demand["family_states"]["vidiq_keywords"] == "PRESENT"
    detail = client.get(f"/api/v1/opportunities/{OPP}").json()
    assert detail["evaluation"]["spanish"]["spanish_demand_state"] == "OBSERVED"
    assert client.get("/api/v1/usage/hasdata").json()["calls_used"] == 1


def test_worker_skips_a_source_whose_gate_is_closed(
    client: TestClient, providers_on: None, open_policy: Callable[..., None], seeded_db: Session
) -> None:
    open_policy("google_trends", "vidiq_api")
    run_id = client.post(f"/api/v1/opportunities/{OPP}/demand", json=BODY).json()["id"]
    seeded_db.query(m.PolicyApproval).filter_by(capability="vidiq_api").delete()
    seeded_db.commit()
    trends, keywords = FakeTrends(), FakeKeywords()
    ctx = HandlerContext(
        settings=get_settings(),
        make_source=lambda: None,  # type: ignore[arg-type,return-value]
        make_vidiq=lambda: keywords,
        make_hasdata=lambda: trends,
    )
    process_once(get_session_factory(), ctx)
    run = client.get(f"/api/v1/research-runs/{run_id}").json()
    assert keywords.calls == []
    assert len(trends.calls) == 1
    assert any(e["code"] == "POLICY_RESTRICTED" for e in run["errors"])


def test_temporal_resilience_endpoint_and_worker(
    client: TestClient, providers_on: None, open_policy: Callable[..., None], seeded_db: Session
) -> None:
    open_policy("vidiq_api")
    opp_id = _annotated_videos(client, seeded_db)
    response = client.post(
        f"/api/v1/opportunities/{opp_id}/temporal-resilience", json={"max_calls": 4}
    )
    assert response.status_code == 202
    assert response.json()["budget"]["vidiq_credits_estimate"] == 20
    assert (
        client.post(
            f"/api/v1/opportunities/{opp_id}/temporal-resilience", json={"max_calls": 99}
        ).status_code
        == 422
    )
    source = FakeHistory()
    ctx = HandlerContext(
        settings=get_settings(),
        make_source=lambda: None,  # type: ignore[arg-type,return-value]
        make_vidiq=lambda: source,
    )
    process_once(get_session_factory(), ctx)
    run = client.get(f"/api/v1/research-runs/{response.json()['id']}").json()
    assert run["status"] == "COMPLETED"
    assert run["coverage"]["videos_measured"] == 4
    assert run["coverage"]["temporal_resilience"]["ratio"] == 1.0


def test_providers_list_shows_hasdata_without_exposing_the_key(
    client: TestClient, providers_on: None
) -> None:
    providers = {p["id"]: p for p in client.get("/api/v1/providers").json()}
    assert providers["google_trends"]["status"] == "CONFIGURED"
    assert "TEST-NO-REAL" not in str(providers)
