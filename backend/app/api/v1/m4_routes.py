"""Rutas de M4: índices orientativos y ranking. Cada ruta exige la compuerta de políticas (T17)."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ProblemError
from app.db.session import get_session
from app.services import evaluation_service, scoring_service
from app.services.opportunity_service import _scores_out

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class RankingRequest(BaseModel):
    opportunity_ids: list[str] = Field(min_length=1, max_length=200)


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/opportunities/{opportunity_id}/scores")
@router.get("/opportunities/{opportunity_id}/scores/detail")
def scores_detail(
    opportunity_id: str, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    scoring_service.require_allowed(session, settings, _now())
    ev = evaluation_service.latest_evaluation(session, opportunity_id)
    if ev is None:
        raise ProblemError(404, "NO_EVALUATION", "Esta oportunidad aún no tiene evaluación")
    scores = _scores_out(session, settings, ev, _now())
    return {
        "formula_version": ev.scores_json.get("formula_version"),
        "evaluation_version": ev.evaluation_version,
        "scores": {k: v.model_dump() for k, v in scores.items()},
        "inputs": ev.scores_json.get("dimensions"),
        "cost_bounds_usd": ev.scores_json.get("cost_bounds_usd"),
    }


@router.post("/opportunities/{opportunity_id}/scores", status_code=201)
def compute_scores(
    opportunity_id: str, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    ev = scoring_service.compute_and_store(session, settings, opportunity_id, _now())
    session.commit()
    return {
        "evaluation_version": ev.evaluation_version,
        "formula_version": ev.scores_json.get("formula_version"),
    }


@router.post("/cohorts/ranking")
def cohort_ranking(
    body: RankingRequest, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Ranking estable de una cohorte. Los índices NULL van al final, nunca como 0."""
    ordered = scoring_service.ranking(session, settings, body.opportunity_ids, _now())
    return {"ranking": [{"opportunity_id": oid, "integrated": value} for oid, value in ordered]}
