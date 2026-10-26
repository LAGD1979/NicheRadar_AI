"""Tres dimensiones de M4: éxito accesible, diferenciación y mantenibilidad (sin Trends)."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services import feasibility_service, scoring_service
from app.services import spanish_service as svc
from app.services.research_service import enqueue_run

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)
OPP = "syn-opp-01"
GOOD_REASON = "Ángulo propio con fuentes verificables y guion original."


def _latest(session: Session) -> m.Evaluation:
    evaluation = session.scalars(
        select(m.Evaluation)
        .where(m.Evaluation.opportunity_id == OPP)
        .order_by(m.Evaluation.evaluation_version.desc())
    ).first()
    assert evaluation is not None
    return evaluation


def _exact_match(
    session: Session, run_id: str, query_id: str, n: int, *, views: int | None, subs: int | None
) -> None:
    channel = m.Channel(
        id=f"ch-sa-{n}",
        youtube_channel_id=f"UCsa{n:08d}",
        title_current=f"Canal {n}",
        subscriber_count=subs,
        subscriber_band="X",
        language_state="UNKNOWN",
        provider="youtube_official",
        observed_at=NOW,
        source_data_type="OFFICIAL",
        owner_authorized=False,
    )
    video = m.Video(
        id=f"vid-sa-{n}",
        youtube_video_id=f"SAVID{n:05d}",
        channel_id=channel.id,
        title=f"[SINTÉTICO] competidor {n}",
        published_at=NOW,
        duration_seconds=900,
        video_type="LONG",
        video_type_evidence="x",
        language_state="es",
        language_confidence="HIGH",
        view_count=views,
        provider="youtube_official",
        observed_at=NOW,
        source_data_type="OFFICIAL",
    )
    session.add_all([channel, video])
    session.flush()
    session.add(
        m.DiscoveryMatch(
            id=f"match-sa-{n}",
            run_id=run_id,
            query_id=query_id,
            video_id=video.id,
            position=n,
            strategy="spanish_validation",
            match_quality="EXACT",
            is_spanish_market=True,
            opportunity_id=OPP,
        )
    )
    session.flush()


def _seed_competitors(session: Session, specs: list[tuple[int | None, int | None]]) -> None:
    run = enqueue_run(
        session,
        kind="demo",
        policy_mode="restricted",
        payload={},
        params={},
        algorithm_version="t",
        budget={},
    )
    query = m.SourceQuery(
        id=str(uuid4()),
        run_id=run.id,
        provider="youtube_official",
        language_requested="es",
        region=None,
        query_text="consulta de prueba",
        window_code="8-30",
        params_json={},
        executed_at=NOW,
        result_count=len(specs),
        pages=1,
        status="OK",
        opportunity_id=OPP,
    )
    session.add(query)
    session.flush()
    for n, (views, subs) in enumerate(specs):
        _exact_match(session, run.id, query.id, n, views=views, subs=subs)


def test_small_channel_success_is_measured_from_reviewed_exact_competitors(
    seeded_db: Session,
) -> None:
    _seed_competitors(
        seeded_db, [(120_000, 8_000), (90_000, 12_000), (400, 2_000), (800_000, 3_000_000)]
    )
    spanish = svc.record_assessment(seeded_db, OPP, None, NOW)
    access = spanish["small_channel_access"]
    assert access["state"] == "OBSERVED"
    assert access["evaluated"] == 4
    assert access["small_channel_successes"] == 2
    assert access["ratio"] == 0.5
    assert _latest(seeded_db).spanish_json["small_channel_access"]["ratio"] == 0.5


def test_small_channel_success_stays_null_with_a_small_sample(seeded_db: Session) -> None:
    _seed_competitors(seeded_db, [(120_000, 8_000), (None, None)])
    access = svc.record_assessment(seeded_db, OPP, None, NOW)["small_channel_access"]
    assert access["state"] == "INSUFFICIENT_SAMPLE"
    assert access["ratio"] is None  # nunca cero por falta de dato


def test_editorial_validation_and_persistence(client: TestClient, seeded_db: Session) -> None:
    url = f"/api/v1/opportunities/{OPP}/editorial"
    body: dict[str, Any] = {
        "differentiation": "HIGH",
        "differentiation_reason": GOOD_REASON,
        "maintainability": "LOW_EFFORT",
        "maintainability_reason": "Datos estables; no requiere actualizaciones frecuentes.",
    }
    assert client.post(url, json={**body, "differentiation_reason": "corto"}).status_code == 422
    assert client.post(url, json={**body, "differentiation": "ENORME"}).status_code == 422
    assert client.post("/api/v1/opportunities/no-existe/editorial", json=body).status_code == 404
    response = client.post(url, json=body)
    assert response.status_code == 201
    assert response.json()["editorial"]["differentiation"]["level"] == "HIGH"
    seeded_db.expire_all()
    stored = _latest(seeded_db).feasibility_json["editorial"]
    assert stored["maintainability"]["level"] == "LOW_EFFORT"
    assert stored["assessed_by"] == "local_owner"


def test_editing_feasibility_does_not_erase_the_editorial_assessment(
    client: TestClient, seeded_db: Session
) -> None:
    client.post(
        f"/api/v1/opportunities/{OPP}/editorial",
        json={
            "differentiation": "MEDIUM",
            "differentiation_reason": GOOD_REASON,
            "maintainability": "MODERATE",
            "maintainability_reason": "Requiere revisar cifras cada trimestre aproximadamente.",
        },
    )
    feasibility_service.save_feasibility(
        seeded_db,
        OPP,
        faceless_state="FACELESS_LIKELY",
        complexity_1_to_5=2,
        rights_risk="LOW",
        rights_notes=None,
        faceless_reason="Narración con ilustraciones propias y mapas generados.",
        human_review_required=True,
        human_minutes_per_video=45,
        ai_pipeline_coverage_pct=70,
        reviewer="t",
        now=NOW,
    )
    seeded_db.commit()
    assert _latest(seeded_db).feasibility_json["editorial"]["differentiation"]["level"] == "MEDIUM"


def test_scores_use_the_three_dimensions_and_the_integrated_index_stays_null(
    seeded_db: Session,
) -> None:
    _seed_competitors(seeded_db, [(120_000, 8_000), (90_000, 12_000), (70_000, 9_000)])
    svc.record_assessment(seeded_db, OPP, None, NOW)
    feasibility_service.save_editorial(
        seeded_db,
        OPP,
        differentiation="HIGH",
        differentiation_reason=GOOD_REASON,
        maintainability="LOW_EFFORT",
        maintainability_reason="Contenido estable; sin cifras que caduquen pronto.",
        reviewer="t",
        now=NOW,
    )
    scores = scoring_service.compute_for_evaluation(_latest(seeded_db), (None, None))
    spanish = scores["dimensions"]["spanish"]
    operational = scores["dimensions"]["operational"]
    assert spanish["exito_accesible"] == 1.0
    assert spanish["diferenciacion"] == 1.0
    assert operational["mantenibilidad"] == 1.0
    # La resiliencia temporal sigue sin serie histórica: el integrado es NULL, no un valor parcial.
    assert scores["dimensions"]["international"]["resiliencia_temporal"] is None
    assert scores["integrated"]["value"] is None
    assert "resiliencia_temporal" in " ".join(scores["international"]["missing"])
