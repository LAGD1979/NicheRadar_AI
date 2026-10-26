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
    def __init__(
        self,
        values: list[int | None] | None = None,
        error: Exception | None = None,
        per_term: dict[str, list[int | None]] | None = None,
    ):
        self.values = values if values is not None else [40] * 52
        self.per_term = per_term or {}
        self.error = error
        self.calls: list[tuple[str, str]] = []  # (términos unidos por coma, país)
        self.closed = False

    def compare_interest(
        self, queries: list[str], *, geo: str = "", **_: Any
    ) -> dict[str, list[TrendPoint]]:
        self.calls.append((",".join(queries), geo))
        if self.error:
            raise self.error
        out: dict[str, list[TrendPoint]] = {}
        for query in queries:
            values = self.per_term.get(query, self.values)
            out[query] = [
                TrendPoint(NOW - timedelta(weeks=len(values) - i), value, False)
                for i, value in enumerate(values)
            ]
        return out

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
        force=True,
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
    # 1 llamada comparable + una de «relacionadas» por término: el tope corta a la segunda.
    outcome = _observe(
        seeded_db,
        keywords=["uno uno", "dos dos", "tres tres"],
        sources=["trends"],
        vidiq=None,
        trends=trends,
        include_related=True,
    )
    assert outcome.outcome == "PAUSED_QUOTA"
    assert len(trends.calls) == 1
    snapshot = demand_service.hasdata_snapshot(seeded_db, get_settings(), NOW)
    assert snapshot["calls_used"] == 2
    assert snapshot["calls_remaining"] == 0
    # Lo medido no se pierde: los tres términos quedaron guardados, solo sin «relacionadas».
    rows = seeded_db.scalars(select(m.DemandObservation)).all()
    assert len(rows) == 3
    assert sum("related" in r.result_json for r in rows) == 1
    monkeypatch.delenv("HASDATA_DAILY_CALL_LIMIT")
    get_settings.cache_clear()


def test_monthly_hasdata_limit_pauses_the_run(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HASDATA_MONTHLY_CALL_LIMIT", "1")
    get_settings.cache_clear()
    first = _observe(seeded_db, sources=["trends"], vidiq=None, keywords=["uno uno"])
    assert first.outcome == "COMPLETED"
    # Otro día del mismo mes: el tope diario alcanza, el mensual no.
    later = NOW + timedelta(days=1) if NOW.day < 28 else NOW - timedelta(days=1)
    second = _observe(
        seeded_db, sources=["trends"], vidiq=None, keywords=["otro otro"], now=later, force=True
    )
    assert second.outcome == "PAUSED_QUOTA"
    snapshot = demand_service.hasdata_snapshot(seeded_db, get_settings(), NOW)
    assert snapshot["calls_month_used"] == 1
    assert snapshot["calls_month_remaining"] == 0
    monkeypatch.delenv("HASDATA_MONTHLY_CALL_LIMIT")
    get_settings.cache_clear()


# --- términos comparables en una sola llamada ----------------------------------------------------


def test_several_terms_go_in_one_call_and_are_stored_as_a_comparison_group(
    seeded_db: Session,
) -> None:
    trends = FakeTrends(per_term={"video ensayo": [60] * 52, "ensayo audiovisual": [30] * 52})
    outcome = _observe(
        seeded_db,
        keywords=["video ensayo", "ensayo audiovisual"],
        sources=["trends"],
        vidiq=None,
        trends=trends,
    )
    assert outcome.hasdata_calls == 1
    assert trends.calls == [("video ensayo,ensayo audiovisual", "")]
    rows = {r.keyword: r for r in seeded_db.scalars(select(m.DemandObservation))}
    assert set(rows) == {"video ensayo", "ensayo audiovisual"}
    group = ["ensayo audiovisual", "video ensayo"]
    assert all(r.result_json["comparison_group"] == group for r in rows.values())
    assert rows["video ensayo"].result_json["share_of_leader"] == 100.0
    assert rows["ensayo audiovisual"].result_json["share_of_leader"] == 50.0
    assert rows["video ensayo"].state == "PRESENT"


def test_a_low_index_next_to_a_stronger_term_is_unknown_not_absent(seeded_db: Session) -> None:
    trends = FakeTrends(per_term={"fuerte fuerte": [90] * 52, "debil debil": [3] * 52})
    _observe(
        seeded_db,
        keywords=["fuerte fuerte", "debil debil"],
        sources=["trends"],
        vidiq=None,
        trends=trends,
    )
    rows = {r.keyword: r for r in seeded_db.scalars(select(m.DemandObservation))}
    assert rows["debil debil"].state == "UNKNOWN"
    assert rows["debil debil"].reason == "LOW_IN_COMPARISON"
    # Medido solo, el mismo índice bajo sí es una señal de que falta demanda.
    _observe(
        seeded_db,
        keywords=["solo solo"],
        sources=["trends"],
        vidiq=None,
        trends=FakeTrends([3] * 52),
    )
    solo = seeded_db.scalars(
        select(m.DemandObservation).where(m.DemandObservation.keyword == "solo solo")
    ).one()
    assert (solo.state, solo.reason) == ("NOT_PRESENT", "LOW_RELATIVE_INTEREST")


def test_a_term_without_data_in_the_group_stays_unknown(seeded_db: Session) -> None:
    trends = FakeTrends(per_term={"con datos": [50] * 52, "sin datos": [None] * 52})
    _observe(
        seeded_db,
        keywords=["con datos", "sin datos"],
        sources=["trends"],
        vidiq=None,
        trends=trends,
    )
    rows = {r.keyword: r for r in seeded_db.scalars(select(m.DemandObservation))}
    assert rows["con datos"].state == "PRESENT"
    assert (rows["sin datos"].state, rows["sin datos"].reason) == ("UNKNOWN", "INSUFFICIENT_DATA")


def test_a_recent_measurement_of_the_same_terms_is_reused(seeded_db: Session) -> None:
    kwargs: dict[str, Any] = {
        "keywords": ["video ensayo", "ensayo audiovisual"],
        "sources": ["trends"],
        "vidiq": None,
    }
    first = FakeTrends()
    _observe(seeded_db, trends=first, **kwargs)
    again = FakeTrends()
    outcome = _observe(seeded_db, trends=again, now=NOW + timedelta(days=3), **kwargs)
    assert again.calls == []
    assert (outcome.hasdata_calls, outcome.reused, outcome.observations) == (0, 1, 0)
    assert sorted(outcome.completed) == [
        "trends:ensayo audiovisual:",
        "trends:video ensayo:",
    ]
    assert seeded_db.scalar(select(func.count()).select_from(m.DemandObservation)) == 2


def test_force_old_measurements_and_different_groups_are_measured_again(
    seeded_db: Session,
) -> None:
    kwargs: dict[str, Any] = {"sources": ["trends"], "vidiq": None}
    _observe(seeded_db, keywords=["video ensayo", "ensayo audiovisual"], **kwargs)
    forced = FakeTrends()
    _observe(
        seeded_db,
        keywords=["video ensayo", "ensayo audiovisual"],
        trends=forced,
        force=True,
        now=NOW + timedelta(days=1),
        **kwargs,
    )
    assert len(forced.calls) == 1
    old = FakeTrends()
    _observe(
        seeded_db,
        keywords=["video ensayo", "ensayo audiovisual"],
        trends=old,
        now=NOW + timedelta(days=9),  # pasó el plazo de reutilización
        **kwargs,
    )
    assert len(old.calls) == 1
    other = FakeTrends()
    # Un grupo distinto no es comparable con el anterior, aunque comparta un término.
    _observe(
        seeded_db,
        keywords=["video ensayo", "documental"],
        trends=other,
        now=NOW + timedelta(days=9, minutes=1),
        **kwargs,
    )
    assert len(other.calls) == 1


def test_related_queries_are_not_reused_when_the_old_measurement_lacks_them(
    seeded_db: Session,
) -> None:
    kwargs: dict[str, Any] = {"keywords": ["video ensayo"], "sources": ["trends"], "vidiq": None}
    _observe(seeded_db, **kwargs)
    with_related = FakeTrends()
    outcome = _observe(
        seeded_db,
        trends=with_related,
        include_related=True,
        now=NOW + timedelta(days=1),
        **kwargs,
    )
    assert len(with_related.calls) == 1
    assert outcome.hasdata_calls == 2


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
    assert client.post(url, json={**BODY, "keywords": ["uno, dos"]}).status_code == 422
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


def test_budget_counts_one_call_for_all_terms_plus_related_per_term(
    client: TestClient, providers_on: None, open_policy: Callable[..., None]
) -> None:
    open_policy("google_trends")
    url = f"/api/v1/opportunities/{OPP}/demand"
    body = {"keywords": ["uno uno", "dos dos", "tres tres"], "sources": ["trends"]}
    plain = client.post(url, json=body).json()["budget"]
    assert (plain["hasdata_calls_estimate"], plain["hasdata_credits_estimate"]) == (1, 10)
    related = client.post(url, json={**body, "include_related": True}).json()["budget"]
    assert (related["hasdata_calls_estimate"], related["hasdata_credits_estimate"]) == (4, 40)
    usage = client.get("/api/v1/usage/hasdata").json()
    assert usage["calls_monthly_limit"] == 90
    assert usage["calls_month_remaining"] == 90


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
