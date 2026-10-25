"""Rutas de M3: modelo de costo, factibilidad revisada, recomendación y exportación."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.db.session import get_session
from app.services import feasibility_service
from app.services import opportunity_service as opp_svc

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
Price = float | None


class CostLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=40)
    quantity: float = Field(ge=0, le=1_000_000)
    prices: dict[Literal["low", "base", "high"], Price] = Field(default_factory=dict)


class CostModelIn(BaseModel):
    duration_minutes: float = Field(gt=0, le=60)
    words_per_minute: int = Field(ge=60, le=220)
    lines: list[CostLineIn] = Field(min_length=1, max_length=20)


class FeasibilityIn(BaseModel):
    faceless_state: str = Field(max_length=30)
    complexity_1_to_5: int | None = Field(default=None, ge=1, le=5)
    rights_risk: str = Field(max_length=10)
    rights_notes: str | None = Field(default=None, max_length=1000)
    faceless_reason: str = Field(min_length=20, max_length=1000)
    human_review_required: bool = True
    human_minutes_per_video: float | None = Field(default=None, ge=0, le=10_000)
    ai_pipeline_coverage_pct: float | None = Field(default=None, ge=0, le=100)


@router.get("/opportunities/{opportunity_id}/cost-model")
def get_cost_model(opportunity_id: str, session: SessionDep) -> dict[str, Any]:
    model = feasibility_service.latest_cost_model(session, opportunity_id)
    if model is None:
        raise ProblemError(
            404, "COST_MODEL_NOT_FOUND", "Esta oportunidad aún no tiene modelo de costo"
        )
    return {
        "version": model.version,
        "params": model.params_json,
        "scenarios": model.scenarios_json,
        "missing": model.missing_json,
        "created_by": model.created_by,
        "created_at": model.created_at,
    }


@router.post("/opportunities/{opportunity_id}/cost-model", status_code=201)
def post_cost_model(opportunity_id: str, body: CostModelIn, session: SessionDep) -> dict[str, Any]:
    """Guarda un modelo de costo. Sin precio en un escenario, su total queda NULL (T15)."""
    model = feasibility_service.save_cost_model(
        session,
        opportunity_id,
        duration_minutes=body.duration_minutes,
        words_per_minute=body.words_per_minute,
        lines=[line.model_dump() for line in body.lines],
        reviewer="local_owner",
        now=_now(),
    )
    session.commit()
    return {
        "version": model.version,
        "scenarios": model.scenarios_json,
        "missing": model.missing_json,
    }


@router.post("/opportunities/{opportunity_id}/feasibility", status_code=201)
def post_feasibility(
    opportunity_id: str, body: FeasibilityIn, session: SessionDep
) -> dict[str, Any]:
    evaluation = feasibility_service.save_feasibility(
        session,
        opportunity_id,
        faceless_state=body.faceless_state,
        complexity_1_to_5=body.complexity_1_to_5,
        rights_risk=body.rights_risk,
        rights_notes=body.rights_notes,
        faceless_reason=body.faceless_reason,
        human_review_required=body.human_review_required,
        human_minutes_per_video=body.human_minutes_per_video,
        ai_pipeline_coverage_pct=body.ai_pipeline_coverage_pct,
        reviewer="local_owner",
        now=_now(),
    )
    session.commit()
    return {
        "evaluation_version": evaluation.evaluation_version,
        "recommendation": evaluation.recommendation,
        "gates": evaluation.reason_codes_json,
    }


@router.get("/exports/opportunities.csv")
def export_csv(
    session: SessionDep,
    q: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=40),
    video_type: str | None = Query(default=None, max_length=10),
    confidence: str | None = Query(default=None, max_length=20),
    saturation_es: str | None = Query(default=None, max_length=20),
    faceless_state: str | None = Query(default=None, max_length=30),
    rights_risk: str | None = Query(default=None, max_length=20),
) -> Response:
    rows = _export_rows(
        session,
        q,
        {
            "status": status,
            "video_type": video_type,
            "confidence": confidence,
            "saturation_es": saturation_es,
            "faceless_state": faceless_state,
            "rights_risk": rights_risk,
        },
    )
    return Response(
        content=feasibility_service.to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oportunidades.csv"'},
    )


@router.get("/exports/opportunities.json")
def export_json(
    session: SessionDep,
    q: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=40),
    video_type: str | None = Query(default=None, max_length=10),
    confidence: str | None = Query(default=None, max_length=20),
    saturation_es: str | None = Query(default=None, max_length=20),
    faceless_state: str | None = Query(default=None, max_length=30),
    rights_risk: str | None = Query(default=None, max_length=20),
) -> Response:
    rows = _export_rows(
        session,
        q,
        {
            "status": status,
            "video_type": video_type,
            "confidence": confidence,
            "saturation_es": saturation_es,
            "faceless_state": faceless_state,
            "rights_risk": rights_risk,
        },
    )
    return Response(
        content=feasibility_service.to_json(rows),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oportunidades.json"'},
    )


def _export_rows(
    session: Session, q: str | None, filters: dict[str, str | None]
) -> list[dict[str, Any]]:
    """Exporta lo que el usuario ve con sus filtros (todas las páginas, hasta 1000 filas)."""
    active = {k: v for k, v in filters.items() if v}
    items: list[dict[str, Any]] = []
    page = 1
    while len(items) < 1000:
        found, total = opp_svc.list_opportunities(
            session, page=page, page_size=100, q=q, filters=active, sort="name"
        )
        items.extend(item.model_dump() for item in found)
        if len(items) >= total or not found:
            break
        page += 1
    return feasibility_service.export_records(session, items)


def _now() -> datetime:
    return datetime.now(UTC)
