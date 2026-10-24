from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.db import models as m

DEMO_DEDUPE_KEY = "demo_research"


def enqueue_demo_run(session: Session, policy_mode: str) -> m.ResearchRun:
    """Crea una corrida DEMO en cola. No llama a ninguna fuente externa."""
    now = datetime.now(UTC)
    run = m.ResearchRun(
        id=str(uuid4()),
        kind="demo",
        status="QUEUED",
        params_json={"dataset": "synthetic_v1", "network": False},
        algorithm_version="m0-demo-1",
        policy_mode=policy_mode,
        started_at=None,
        finished_at=None,
        errors_json=[],
        coverage_json={},
        budget_json={"youtube_search_calls": 0, "ai_usd": 0},
    )
    session.add(run)
    session.add(
        m.RunTask(
            id=str(uuid4()),
            run_id=run.id,
            task_type="demo_research",
            dedupe_key=DEMO_DEDUPE_KEY,
            status="PENDING",
            attempts=0,
            next_attempt_at=now,
            payload_json={"dataset": "synthetic_v1"},
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
            details_redacted_json={"kind": "demo"},
        )
    )
    session.flush()
    return run


def get_run(session: Session, run_id: str) -> m.ResearchRun:
    run = session.get(m.ResearchRun, run_id)
    if run is None:
        raise ProblemError(404, "RUN_NOT_FOUND", "Corrida no encontrada")
    return run


def count_runs(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(m.ResearchRun)) or 0)
