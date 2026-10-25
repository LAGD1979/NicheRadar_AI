"""Evaluación append-only (spec §6.1, §6.2): cada cambio crea una versión nueva.

La recomendación y las compuertas se recalculan siempre a partir de la versión resultante.
Lo que no cambió se copia de la versión anterior; nunca se inventa un valor.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.db import models as m
from app.domain.decision import Decision, DecisionInput, decide


def latest_evaluation(session: Session, opportunity_id: str) -> m.Evaluation | None:
    return session.scalars(
        select(m.Evaluation)
        .where(m.Evaluation.opportunity_id == opportunity_id)
        .order_by(m.Evaluation.evaluation_version.desc())
    ).first()


def decision_for(
    spanish: dict[str, Any],
    international: dict[str, Any],
    feasibility: dict[str, Any],
    confidence: str | None,
) -> Decision:
    queries = spanish.get("query_coverage_count")
    return decide(
        DecisionInput(
            replication=_text(international.get("replication_state")),
            spanish_decision=_text(spanish.get("entry_decision")),
            demand=_text(spanish.get("spanish_demand_state")),
            queries_run=int(queries) if isinstance(queries, int) else 0,
            confidence=confidence,
            faceless=_text(feasibility.get("faceless_state")),
            complexity=_int(feasibility.get("complexity_1_to_5")),
            rights=_text(feasibility.get("rights_risk")),
        )
    )


def append_evaluation(
    session: Session,
    opportunity_id: str,
    *,
    now: datetime,
    source: str,
    run_id: str | None = None,
    spanish: dict[str, Any] | None = None,
    international: dict[str, Any] | None = None,
    feasibility: dict[str, Any] | None = None,
    confidence: str | None = None,
    scores: dict[str, Any] | None = None,
) -> m.Evaluation:
    opp = session.get(m.Opportunity, opportunity_id)
    if opp is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    previous = latest_evaluation(session, opportunity_id)
    spanish_json = (
        spanish if spanish is not None else dict(previous.spanish_json if previous else {})
    )
    international_json = (
        international
        if international is not None
        else dict(previous.international_json if previous else {})
    )
    feasibility_json = (
        feasibility
        if feasibility is not None
        else dict(previous.feasibility_json if previous else {})
    )
    confidence_value = confidence or (previous.confidence if previous else "INSUFFICIENT")
    decision = decision_for(spanish_json, international_json, feasibility_json, confidence_value)
    evaluation = m.Evaluation(
        id=str(uuid4()),
        opportunity_id=opportunity_id,
        run_id=run_id,
        evaluation_version=(previous.evaluation_version if previous else 0) + 1,
        international_json=international_json,
        spanish_json=spanish_json,
        feasibility_json=feasibility_json,
        scores_json=scores
        if scores is not None
        else (dict(previous.scores_json) if previous else {}),
        confidence=confidence_value,
        reason_codes_json=decision.gates,
        recommendation=decision.recommendation,
        metric_policy_state="RESTRICTED",
        source_data_type=source,
        observed_at=now,
    )
    session.add(evaluation)
    opp.last_evaluated_at = now
    session.flush()
    return evaluation


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
