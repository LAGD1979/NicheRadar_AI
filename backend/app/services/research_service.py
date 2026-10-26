from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.db import models as m

TASK_TYPES = {
    "demo": "demo_research",
    "discovery": "youtube_discovery",
    "vidiq": "vidiq_discovery",
    "demand": "demand_observation",
    "history": "vidiq_history",
    "purge": "retention_purge",
    "spanish_plan": "spanish_plan",
    "spanish_validation": "spanish_validation",
}
PAUSED = "PAUSED_QUOTA"


def enqueue_run(
    session: Session,
    *,
    kind: str,
    policy_mode: str,
    payload: dict[str, Any],
    params: dict[str, Any],
    algorithm_version: str,
    budget: dict[str, Any],
) -> m.ResearchRun:
    """Crea la corrida y su tarea en cola. El trabajo lo ejecuta el worker, no el request."""
    if kind not in TASK_TYPES:
        raise ProblemError(422, "UNKNOWN_KIND", "Tipo de corrida desconocido")
    now = datetime.now(UTC)
    run = m.ResearchRun(
        id=str(uuid4()),
        kind=kind,
        status="QUEUED",
        params_json=params,
        algorithm_version=algorithm_version,
        policy_mode=policy_mode,
        started_at=None,
        finished_at=None,
        errors_json=[],
        coverage_json={},
        budget_json=budget,
    )
    session.add(run)
    session.add(
        m.RunTask(
            id=str(uuid4()),
            run_id=run.id,
            task_type=TASK_TYPES[kind],
            dedupe_key=TASK_TYPES[kind],
            status="PENDING",
            attempts=0,
            next_attempt_at=now,
            payload_json=payload,
            result_json={},
        )
    )
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=run.id,
            actor="local_owner",
            event_type="RUN_REQUESTED",
            object_type="research_run",
            object_id=run.id,
            details_redacted_json={"kind": kind},
        )
    )
    session.flush()
    return run


def enqueue_demo_run(session: Session, policy_mode: str) -> m.ResearchRun:
    return enqueue_run(
        session,
        kind="demo",
        policy_mode=policy_mode,
        payload={"dataset": "synthetic_v1"},
        params={"dataset": "synthetic_v1", "network": False},
        algorithm_version="m0-demo-1",
        budget={"youtube_units": 0, "ai_usd": 0},
    )


def get_run(session: Session, run_id: str) -> m.ResearchRun:
    run = session.get(m.ResearchRun, run_id)
    if run is None:
        raise ProblemError(404, "RUN_NOT_FOUND", "Corrida no encontrada")
    return run


def resume_run(session: Session, run_id: str) -> m.ResearchRun:
    """Reanuda una corrida pausada por cuota. El progreso ya completado no se repite."""
    run = get_run(session, run_id)
    if run.status != PAUSED:
        raise ProblemError(409, "NOT_RESUMABLE", "Solo se reanudan corridas pausadas por cuota")
    task = session.scalars(select(m.RunTask).where(m.RunTask.run_id == run_id)).one()
    task.status = "PENDING"
    task.locked_at = None
    task.next_attempt_at = datetime.now(UTC)
    run.status = "QUEUED"
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=run_id,
            actor="local_owner",
            event_type="RUN_RESUMED",
            object_type="research_run",
            object_id=run_id,
            details_redacted_json={},
        )
    )
    session.flush()
    return run


def run_events(session: Session, run_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(m.AuditEvent)
        .where(m.AuditEvent.run_id == run_id)
        .order_by(m.AuditEvent.created_at, m.AuditEvent.id)
    ).all()
    return [
        {
            "event_type": r.event_type,
            "actor": r.actor,
            "created_at": r.created_at,
            "details": r.details_redacted_json,
        }
        for r in rows
    ]


def count_runs(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(m.ResearchRun)) or 0)
