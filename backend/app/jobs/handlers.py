from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models as m


def run_demo_research(session: Session, run_id: str) -> dict[str, Any]:
    """Resume el dataset sintético en la corrida. No hace red ni llamadas a APIs.

    Idempotente: si la corrida ya está completada, no vuelve a escribir.
    """
    run = session.get(m.ResearchRun, run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {run_id}")
    if run.status == "COMPLETED":
        return {"skipped": "already_completed"}

    language_rows = session.execute(
        select(m.Video.language_state, func.count()).group_by(m.Video.language_state)
    ).all()
    by_language = {str(state): int(count) for state, count in language_rows}
    channels = session.scalar(select(func.count()).select_from(m.Channel)) or 0
    now = datetime.now(UTC)
    run.status = "COMPLETED"
    run.started_at = run.started_at or now
    run.finished_at = now
    run.coverage_json = {
        "dataset": "synthetic_v1",
        "network": False,
        "channels": int(channels),
        "videos_by_language_state": by_language,
        "note": "Cobertura sintética; no representa el universo de YouTube.",
    }
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=run_id,
            actor="worker",
            event_type="RUN_COMPLETED",
            object_type="research_run",
            object_id=run_id,
            details_redacted_json={"task": "demo_research"},
        )
    )
    return {"completed": True, "channels": int(channels)}
