"""Mercado español M2 contra PostgreSQL. Sin red: la IA y YouTube son dobles de prueba."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ProblemError
from app.db import models as m
from app.domain.search_plan import SpanishSearchPlan
from app.jobs import worker
from app.jobs.handlers import HANDLERS, HandlerContext
from app.services import spanish_service as svc
from app.services.research_service import enqueue_run
from tests.fakes import FakeSource, synthetic_channel, synthetic_hit, synthetic_video

NOW = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
QUERIES = [
    "historia con mapas",
    "conflictos en mapas",
    "mapas históricos",
    "guerra en mapas",
    "historia en mapas animados",
]


class FakeAI:
    """Devuelve una respuesta fija. Es un doble de prueba, no una fuente de datos."""

    model = "modelo-de-prueba"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, system: str, user: str) -> str:
        return self.text

    def close(self) -> None:
        return None


def _plan_json(
    source_ids: list[str] | None = None, queries: list[str] | None = None
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "canonical_concept_es": "Historia explicada con mapas",
        "same_format_definition": "Relato narrado sobre conflictos con mapas animados.",
        "query_groups": [
            {"region": "ALL_ES", "language": "es", "queries": queries or QUERIES},
            {"region": "LATAM", "language": "es", "queries": ["mapas de historia"]},
        ],
        "adjacent_but_distinct": ["documentales sin mapas"],
        "localization_notes": [],
        "source_ids": source_ids if source_ids is not None else ["V:SYNV01"],
    }


def _draft(**overrides: Any) -> SpanishSearchPlan:
    return SpanishSearchPlan.model_validate(_plan_json() | overrides)


# --- oportunidades y anotaciones -------------------------------------------------------------


def test_same_format_in_another_niche_is_another_opportunity(seeded_db: Session) -> None:
    # T09: mismo formato, nicho distinto: dos oportunidades, no se fusionan.
    # Combinaciones que no existen en el fixture (niche-01 x fmt-02 y niche-02 x fmt-02 sí existen).
    a, created_a = svc.ensure_opportunity(
        seeded_db,
        niche_id="syn-niche-03",
        format_id="syn-fmt-02",
        target_lang="es",
        video_type="LONG",
    )
    b, created_b = svc.ensure_opportunity(
        seeded_db,
        niche_id="syn-niche-05",
        format_id="syn-fmt-02",
        target_lang="es",
        video_type="LONG",
    )
    assert created_a and created_b and a.id != b.id


def test_two_videos_annotated_to_one_format_share_one_opportunity(seeded_db: Session) -> None:
    # T08: varios videos del mismo formato forman un solo grupo; cada uno conserva su etiqueta.
    seeded_db.add(synthetic_video_row("SYNV92", "syn-ch-02", "pt"))
    seeded_db.commit()
    ann1, opp1 = svc.annotate_video(
        seeded_db,
        video_id="syn-vid-03",
        niche_id="syn-niche-01",
        format_id="syn-fmt-01",
        confidence="HIGH",
        rationale="Mismo formato de relato con ilustraciones.",
        reviewer="t",
    )
    ann2, opp2 = svc.annotate_video(
        seeded_db,
        video_id=synthetic_video_row_id("SYNV92"),
        niche_id="syn-niche-01",
        format_id="syn-fmt-01",
        confidence="MEDIUM",
        rationale="Mismo formato, otra expresión en portugués.",
        reviewer="t",
    )
    seeded_db.commit()
    assert opp1.id == opp2.id
    assert (
        seeded_db.scalar(
            select(func.count())
            .select_from(m.VideoAnnotation)
            .where(m.VideoAnnotation.opportunity_id == opp1.id)
        )
        == 2
    )


def synthetic_video_row(yt_id: str, channel_id: str, audio: str) -> m.Video:
    return m.Video(
        id=synthetic_video_row_id(yt_id),
        youtube_video_id=yt_id,
        channel_id=channel_id,
        title=f"[SINTÉTICO] {yt_id}",
        published_at=NOW,
        duration_seconds=720,
        video_type="LONG",
        video_type_evidence="x",
        language_state=audio,
        language_confidence="HIGH",
        view_count=10,
        url=None,
        provider="synthetic_fixture",
        observed_at=NOW,
        source_data_type="SYNTHETIC",
        availability="AVAILABLE",
        owner_authorized=False,
    )


def synthetic_video_row_id(yt_id: str) -> str:
    return f"row-{yt_id}"


def test_annotating_an_unclear_video_type_is_refused(seeded_db: Session) -> None:
    with pytest.raises(ProblemError) as info:
        svc.annotate_video(
            seeded_db,
            video_id="syn-vid-19",
            niche_id="syn-niche-01",
            format_id="syn-fmt-01",
            confidence="HIGH",
            rationale="Intento de etiquetar un Short ambiguo.",
            reviewer="t",
        )
    assert info.value.code == "VIDEO_TYPE_UNCLEAR"


# --- planes generados por IA -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("esto no es json", "INVALID_JSON"),
        ('{"schema_version": "1.0"}', "INVALID_PLAN"),
        (json.dumps(_plan_json(source_ids=["V:INVENTADO"])), "INVALID_EVIDENCE_REF"),
        (
            json.dumps(
                _plan_json(
                    queries=["mira https://ejemplo.invalid", "dos", "tres", "cuatro", "cinco"]
                )
            ),
            "INVALID_PLAN",
        ),
    ],
)
def test_invalid_ai_output_is_kept_for_review_without_facts(
    seeded_db: Session, raw: str, error: str
) -> None:
    # T13: un ID inventado, una URL o JSON roto no se guardan como plan válido.
    plan = svc.generate_plan_with_ai(seeded_db, FakeAI(raw), "syn-opp-01")  # type: ignore[arg-type]
    seeded_db.commit()
    assert plan.status == "NEEDS_REVIEW"
    assert plan.error_code == error
    assert plan.plan_json == {}


def test_valid_ai_plan_waits_for_human_approval(seeded_db: Session) -> None:
    plan = svc.generate_plan_with_ai(seeded_db, FakeAI(json.dumps(_plan_json())), "syn-opp-01")  # type: ignore[arg-type]
    seeded_db.commit()
    assert plan.status == "PENDING_REVIEW"
    assert plan.origin == "AI"
    assert plan.model_version == "modelo-de-prueba"
    assert plan.prompt_version == "P2-1"


def test_approved_plan_is_locked_and_a_new_approval_supersedes_the_old(seeded_db: Session) -> None:
    first = svc.create_manual_plan(seeded_db, "syn-opp-01", _draft())
    svc.update_plan(seeded_db, first.id, _draft(), approve=True, reviewer="t")
    second = svc.create_manual_plan(
        seeded_db, "syn-opp-01", _draft(canonical_concept_es="Versión dos del plan")
    )
    svc.update_plan(
        seeded_db,
        second.id,
        _draft(canonical_concept_es="Versión dos del plan"),
        approve=True,
        reviewer="t",
    )
    seeded_db.commit()
    assert first.status == "SUPERSEDED"
    assert second.status == "APPROVED"
    with pytest.raises(ProblemError) as info:
        svc.update_plan(seeded_db, first.id, _draft(), approve=False, reviewer="t")
    assert info.value.code == "PLAN_LOCKED"


def test_manual_plan_citing_unknown_source_is_refused(seeded_db: Session) -> None:
    with pytest.raises(ProblemError) as info:
        svc.create_manual_plan(seeded_db, "syn-opp-01", _draft(source_ids=["V:NO-EXISTE"]))
    assert info.value.code == "INVALID_EVIDENCE_REF"


# --- validación en español -------------------------------------------------------------------


def _approved(session: Session) -> m.SpanishSearchPlan:
    plan = svc.create_manual_plan(session, "syn-opp-01", _draft())
    svc.update_plan(session, plan.id, _draft(), approve=True, reviewer="t")
    session.commit()
    return plan


def _es_source() -> FakeSource:
    hits = {
        q: [synthetic_hit("SYNV90", "SYNCH90"), synthetic_hit("SYNV91", "SYNCH90")] for q in QUERIES
    }
    return FakeSource(
        hits=hits,
        videos=[
            synthetic_video("SYNV90", "SYNCH90", audio="es"),
            synthetic_video("SYNV91", "SYNCH90", audio="pt"),
        ],
        channels=[synthetic_channel("SYNCH90")],
    )


def _run_validation(
    session: Session, plan: m.SpanishSearchPlan, source: FakeSource, windows: list[str]
) -> m.ResearchRun:
    run = enqueue_run(
        session,
        kind="spanish_validation",
        policy_mode="restricted",
        payload={
            "opportunity_id": "syn-opp-01",
            "plan_id": plan.id,
            "windows": windows,
            "max_search_calls": 20,
            "pages_per_query": 1,
        },
        params={},
        algorithm_version="test",
        budget={},
    )
    task = session.scalars(select(m.RunTask).where(m.RunTask.run_id == run.id)).one()
    ctx = HandlerContext(settings=Settings(), make_source=lambda: source)
    outcome = HANDLERS["spanish_validation"](session, task, ctx)
    assert outcome == "COMPLETED"
    session.commit()
    return run


def test_validation_counts_only_spanish_verified_videos_and_is_not_low_without_review(
    seeded_db: Session,
) -> None:
    plan = _approved(seeded_db)
    source = _es_source()
    _run_validation(seeded_db, plan, source, ["8-30", "31-90"])
    coverage = svc.coverage_for(seeded_db, "syn-opp-01")
    # 6 consultas del plan (5 ALL_ES + 1 LATAM) x 2 ventanas
    assert coverage.queries_run == 12
    assert coverage.query_variants == 6
    assert coverage.es_verified_videos == 1  # SYNV90 es español; SYNV91 (audio pt) no cuenta
    assert coverage.reviewed_matches == 0
    latest = seeded_db.scalars(
        select(m.Evaluation)
        .where(m.Evaluation.opportunity_id == "syn-opp-01")
        .order_by(m.Evaluation.evaluation_version.desc())
    ).first()
    assert latest is not None
    assert latest.spanish_json["saturation_state"] == "UNKNOWN"
    assert latest.spanish_json["spanish_demand_state"] == "UNPROVEN"
    assert latest.spanish_json["entry_decision"] == "DEMAND_UNPROVEN"  # T11


def test_unreviewed_matches_are_not_exact_and_review_recalculates(seeded_db: Session) -> None:
    plan = _approved(seeded_db)
    _run_validation(seeded_db, plan, _es_source(), ["8-30", "31-90"])
    match = seeded_db.scalars(
        select(m.DiscoveryMatch).where(
            m.DiscoveryMatch.opportunity_id == "syn-opp-01",
            m.DiscoveryMatch.is_spanish_market.is_(True),
        )
    ).first()
    assert match is not None and match.match_quality == "UNREVIEWED"
    svc.review_match(seeded_db, match.id, "EXACT", reviewer="t")
    seeded_db.commit()
    latest = seeded_db.scalars(
        select(m.Evaluation)
        .where(m.Evaluation.opportunity_id == "syn-opp-01")
        .order_by(m.Evaluation.evaluation_version.desc())
    ).first()
    assert latest is not None
    assert latest.spanish_json["saturation_state"] == "MEDIUM"  # un competidor exacto confirmado
    assert latest.spanish_json["exact_matches"] == 1


def test_validation_requires_an_approved_plan(seeded_db: Session) -> None:
    draft = svc.create_manual_plan(seeded_db, "syn-opp-01", _draft())
    seeded_db.commit()
    with pytest.raises(ProblemError) as info:
        svc.approved_plan(seeded_db, draft.id, "syn-opp-01")
    assert info.value.code == "PLAN_NOT_APPROVED"


def test_evaluation_history_is_append_only(seeded_db: Session) -> None:
    plan = _approved(seeded_db)
    before = seeded_db.scalar(
        select(func.count())
        .select_from(m.Evaluation)
        .where(m.Evaluation.opportunity_id == "syn-opp-01")
    )
    _run_validation(seeded_db, plan, _es_source(), ["8-30", "31-90"])
    after = seeded_db.scalar(
        select(func.count())
        .select_from(m.Evaluation)
        .where(m.Evaluation.opportunity_id == "syn-opp-01")
    )
    assert after == (before or 0) + 1
    original = seeded_db.get(m.Evaluation, "syn-eval-01")
    assert (
        original is not None and original.evaluation_version == 1
    )  # la versión anterior no se toca


# --- API M2 ----------------------------------------------------------------------------------


def test_generate_plan_without_ai_is_refused(client: TestClient) -> None:
    response = client.post("/api/v1/opportunities/syn-opp-01/search-plans/generate")
    assert response.status_code == 409
    assert response.json()["code"] == "AI_NOT_CONFIGURED"


def test_validation_without_youtube_key_is_refused(client: TestClient) -> None:
    plan = client.post("/api/v1/opportunities/syn-opp-01/search-plans", json=_plan_json()).json()
    client.patch(f"/api/v1/search-plans/{plan['id']}", json={"plan": _plan_json(), "approve": True})
    response = client.post(
        "/api/v1/opportunities/syn-opp-01/validate-spanish",
        json={
            "plan_id": plan["id"],
            "windows": ["8-30"],
            "max_search_calls": 5,
            "pages_per_query": 1,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PROVIDER_NOT_CONFIGURED"


def test_manual_plan_approval_and_competition_endpoints(client: TestClient) -> None:
    created = client.post("/api/v1/opportunities/syn-opp-01/search-plans", json=_plan_json())
    assert created.status_code == 201
    plan_id = created.json()["id"]
    approved = client.patch(
        f"/api/v1/search-plans/{plan_id}", json={"plan": _plan_json(), "approve": True}
    )
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["origin"] == "HUMAN"
    locked = client.patch(
        f"/api/v1/search-plans/{plan_id}", json={"plan": _plan_json(), "approve": False}
    )
    assert locked.status_code == 409
    competition = client.get("/api/v1/opportunities/syn-opp-01/competition").json()
    assert competition["coverage"]["exact_matches"] == 0
    assert competition["matches"] == []


def test_taxonomy_and_opportunity_creation(client: TestClient) -> None:
    tax = client.get("/api/v1/taxonomy").json()
    assert len(tax["niches"]) == 5 and len(tax["formats"]) == 4
    body = {"niche_id": "syn-niche-03", "format_id": "syn-fmt-02", "video_type": "LONG"}
    first = client.post("/api/v1/opportunities", json=body).json()
    second = client.post("/api/v1/opportunities", json=body).json()
    assert first["created"] is True and second["created"] is False and first["id"] == second["id"]


def test_worker_runs_plan_handler_with_ai_factory(seeded_db: Session) -> None:
    run = enqueue_run(
        seeded_db,
        kind="spanish_plan",
        policy_mode="restricted",
        payload={"opportunity_id": "syn-opp-01"},
        params={},
        algorithm_version="test",
        budget={},
    )
    seeded_db.commit()
    ctx = HandlerContext(
        settings=get_settings(),
        make_source=lambda: FakeSource(),
        make_ai=lambda: FakeAI(json.dumps(_plan_json())),
    )  # type: ignore[arg-type,return-value]
    assert worker.process_once(worker.get_session_factory(), ctx) is True
    seeded_db.expire_all()
    stored = seeded_db.get(m.ResearchRun, run.id)
    assert stored is not None and stored.status == "COMPLETED"
    assert stored.coverage_json["plan_status"] == "PENDING_REVIEW"
