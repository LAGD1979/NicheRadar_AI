"""Factibilidad, costo y exportación (M3). Las valoraciones las pone una persona, con motivo."""

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.db import models as m
from app.domain import costs
from app.services import evaluation_service

FACELESS_STATES = ("FACELESS_CONFIRMED", "FACELESS_LIKELY", "MIXED", "NOT_FACELESS", "UNKNOWN")
RIGHTS_STATES = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
EXPORT_WARNING = (
    "Datos de terceros: caducan a los 29 días y no son datos oficiales de YouTube. "
    "Las estimaciones de costo son de la persona que las escribió."
)


def neutralize(value: Any) -> Any:
    """Impide que una celda de CSV se interprete como fórmula (T20)."""
    if isinstance(value, str) and value.startswith(CSV_INJECTION_PREFIXES):
        return "'" + value
    return value


# --- costos ----------------------------------------------------------------------------------


def latest_cost_model(session: Session, opportunity_id: str) -> m.CostModel | None:
    return session.scalars(
        select(m.CostModel)
        .where(m.CostModel.opportunity_id == opportunity_id)
        .order_by(m.CostModel.version.desc())
    ).first()


def save_cost_model(
    session: Session,
    opportunity_id: str,
    *,
    duration_minutes: float,
    words_per_minute: int,
    lines: list[dict[str, Any]],
    reviewer: str,
    now: datetime,
) -> m.CostModel:
    if session.get(m.Opportunity, opportunity_id) is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    parsed = [
        costs.CostLine(
            name=str(line["name"]),
            unit=str(line["unit"]),
            quantity=float(line["quantity"]),
            prices={k: (None if v is None else float(v)) for k, v in line["prices"].items()},
        )
        for line in lines
    ]
    result = costs.compute(parsed)
    previous = latest_cost_model(session, opportunity_id)
    model = m.CostModel(
        id=str(uuid4()),
        opportunity_id=opportunity_id,
        version=(previous.version if previous else 0) + 1,
        params_json={
            "duration_minutes": duration_minutes,
            "words_per_minute": words_per_minute,
            "planned_words": costs.planned_words(duration_minutes, words_per_minute),
            "lines": lines,
        },
        scenarios_json={"usd_per_video": result.totals, "currency": "USD", "estimated": True},
        missing_json=result.missing,
        created_by=reviewer,
    )
    session.add(model)
    session.flush()
    _refresh_feasibility_costs(session, opportunity_id, result.totals, reviewer, now)
    return model


def _refresh_feasibility_costs(
    session: Session,
    opportunity_id: str,
    totals: dict[str, float | None],
    reviewer: str,
    now: datetime,
) -> None:
    previous = evaluation_service.latest_evaluation(session, opportunity_id)
    feasibility = dict(previous.feasibility_json) if previous else {}
    feasibility["usd_per_video_scenarios"] = totals
    feasibility["costs_are_estimates"] = True
    feasibility["costs_entered_by"] = reviewer
    evaluation_service.append_evaluation(
        session, opportunity_id, now=now, source="HUMAN", feasibility=feasibility
    )


# --- factibilidad ----------------------------------------------------------------------------


def save_feasibility(
    session: Session,
    opportunity_id: str,
    *,
    faceless_state: str,
    complexity_1_to_5: int | None,
    rights_risk: str,
    rights_notes: str | None,
    faceless_reason: str,
    human_review_required: bool,
    human_minutes_per_video: float | None,
    ai_pipeline_coverage_pct: float | None,
    reviewer: str,
    now: datetime,
) -> m.Evaluation:
    if faceless_state not in FACELESS_STATES or rights_risk not in RIGHTS_STATES:
        raise ProblemError(422, "INVALID_STATE", "Estado no válido")
    if rights_risk in ("MEDIUM", "HIGH") and not (rights_notes and len(rights_notes.strip()) >= 20):
        raise ProblemError(
            422,
            "RIGHTS_REASON_REQUIRED",
            "Un riesgo de derechos medio o alto necesita una explicación de 20 caracteres o más.",
        )
    previous = evaluation_service.latest_evaluation(session, opportunity_id)
    scenarios = (
        previous.feasibility_json.get("usd_per_video_scenarios") if previous else None
    ) or {
        "low": None,
        "base": None,
        "high": None,
    }
    feasibility = {
        "faceless_state": faceless_state,
        "faceless_reason": faceless_reason.strip(),
        "complexity_1_to_5": complexity_1_to_5,
        "rights_risk": rights_risk,
        "rights_notes": (rights_notes or "").strip() or None,
        "human_review_required": human_review_required,
        "human_minutes_per_video": human_minutes_per_video,
        "ai_pipeline_coverage_pct": ai_pipeline_coverage_pct,
        "usd_per_video_scenarios": scenarios,
        "costs_are_estimates": True,
        "assessed_by": reviewer,
    }
    return evaluation_service.append_evaluation(
        session, opportunity_id, now=now, source="HUMAN", feasibility=feasibility
    )


# --- exportación -----------------------------------------------------------------------------


EXPORT_COLUMNS = (
    "id",
    "niche",
    "format",
    "target_lang",
    "video_type",
    "status",
    "recommendation",
    "gates",
    "confidence",
    "saturation_es",
    "spanish_demand_state",
    "entry_decision",
    "faceless_state",
    "complexity_1_to_5",
    "rights_risk",
    "usd_base",
    "data_source",
    "observed_at",
    "warning",
)


def export_records(session: Session, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas de exportación: recomendación, compuertas y costo base de cada oportunidad."""
    out: list[dict[str, Any]] = []
    for item in items:
        ev = evaluation_service.latest_evaluation(session, str(item["id"]))
        feasibility = ev.feasibility_json if ev else {}
        scenarios = feasibility.get("usd_per_video_scenarios") or {}
        out.append(
            {
                "id": item["id"],
                "niche": item["niche"],
                "format": item["format"],
                "target_lang": item["target_lang"],
                "video_type": item["video_type"],
                "status": item["status"],
                "recommendation": ev.recommendation if ev else "",
                "gates": ", ".join(ev.reason_codes_json) if ev else "",
                "confidence": item["confidence"] or "",
                "saturation_es": item["saturation_es"] or "",
                "spanish_demand_state": item["spanish_demand_state"] or "",
                "entry_decision": item["entry_decision"] or "",
                "faceless_state": item["faceless_state"] or "",
                "complexity_1_to_5": item["complexity_1_to_5"]
                if item["complexity_1_to_5"] is not None
                else "",
                "rights_risk": item["rights_risk"] or "",
                "usd_base": scenarios.get("base") if scenarios.get("base") is not None else "",
                "data_source": item["data_source"],
                "observed_at": item["observed_at"].isoformat() if item["observed_at"] else "",
                "warning": EXPORT_WARNING,
            }
        )
    return out


def to_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(EXPORT_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: neutralize(row[k]) for k in EXPORT_COLUMNS})
    return buffer.getvalue()


def to_json(rows: list[dict[str, Any]]) -> str:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "warning": EXPORT_WARNING,
        "items": rows,
    }
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)
