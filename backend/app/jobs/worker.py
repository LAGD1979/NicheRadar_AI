"""Worker persistente: toma tareas de `run_tasks` con bloqueo transaccional.

- `FOR UPDATE SKIP LOCKED` evita que dos workers tomen la misma tarea.
- Una tarea RUNNING con arrendamiento vencido (worker caído) se recupera (T21, recuperación).
- Reintentos finitos; al agotarlos, la tarea y la corrida quedan FAILED con el error.
- Un resultado PAUSED_QUOTA deja la corrida pausada hasta que el usuario la reanude (spec §9.3).
"""

import signal
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db import models as m
from app.db.session import get_session_factory
from app.jobs.handlers import HANDLERS, HandlerContext
from app.providers.factory import build_youtube_source

LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 3
POLL_SECONDS = 2.0

log = structlog.get_logger("worker")


def default_context(settings: Settings | None = None) -> HandlerContext:
    cfg = settings or get_settings()
    return HandlerContext(settings=cfg, make_source=lambda: build_youtube_source(cfg))


def _claim(session: Session, now: datetime) -> tuple[str, str, str] | None:
    stmt = (
        select(m.RunTask)
        .where(
            m.RunTask.next_attempt_at <= now,
            or_(
                m.RunTask.status == "PENDING",
                and_(m.RunTask.status == "RUNNING", m.RunTask.locked_at < now - LEASE),
            ),
        )
        .order_by(m.RunTask.next_attempt_at, m.RunTask.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = session.scalars(stmt).first()
    if task is None:
        return None
    task.status = "RUNNING"
    task.locked_at = now
    task.attempts += 1
    run = session.get(m.ResearchRun, task.run_id)
    if run is not None:
        run.status = "RUNNING"
        run.started_at = run.started_at or now
    return task.id, task.run_id, task.task_type


def process_once(factory: sessionmaker[Session], ctx: HandlerContext | None = None) -> bool:
    """Procesa como máximo una tarea. Devuelve False si no había nada que hacer."""
    handler_ctx = ctx or default_context()
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        claimed = _claim(session, now)
    if claimed is None:
        return False
    task_id, run_id, task_type = claimed

    try:
        with factory() as session, session.begin():
            task = session.get(m.RunTask, task_id)
            if task is None:
                raise LookupError(f"Tarea desaparecida: {task_id}")
            outcome = HANDLERS[task_type](session, task, handler_ctx)
            _apply_outcome(session, task_id, run_id, outcome, datetime.now(UTC))
        log.info("task_finished", task_id=task_id, task_type=task_type, outcome=outcome)
    except Exception as exc:
        _record_failure(factory, task_id, run_id, type(exc).__name__, now)
    return True


def _apply_outcome(
    session: Session, task_id: str, run_id: str, outcome: str, now: datetime
) -> None:
    task = session.get(m.RunTask, task_id)
    run = session.get(m.ResearchRun, run_id)
    if task is None or run is None:
        raise LookupError("Tarea o corrida desaparecida")
    task.locked_at = None
    task.error_class = None
    if outcome == "PAUSED_QUOTA":
        task.status = "PAUSED_QUOTA"
        run.status = "PAUSED_QUOTA"
        return
    task.status = "FAILED" if outcome == "FAILED" else "SUCCEEDED"
    task.result_json = {**task.result_json, "outcome": outcome}
    run.status = outcome if outcome in ("COMPLETED", "PARTIAL", "FAILED") else "COMPLETED"
    run.finished_at = now


def _record_failure(
    factory: sessionmaker[Session], task_id: str, run_id: str, error_class: str, now: datetime
) -> None:
    with factory() as session, session.begin():
        task = session.get(m.RunTask, task_id)
        if task is None:
            return
        task.error_class = error_class
        task.locked_at = None
        if task.attempts >= MAX_ATTEMPTS:
            task.status = "FAILED"
            run = session.get(m.ResearchRun, run_id)
            if run is not None:
                run.status = "FAILED"
                run.finished_at = now
                run.errors_json = [*run.errors_json, {"task": task.task_type, "code": error_class}]
            log.error("task_failed", task_id=task_id, error_class=error_class)
        else:
            task.status = "PENDING"
            task.next_attempt_at = now + timedelta(seconds=2**task.attempts)
            log.warning("task_retry_scheduled", task_id=task_id, error_class=error_class)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stop = threading.Event()

    def _request_stop(signum: int, _frame: Any) -> None:
        log.info("stop_requested", signal=signum)
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    factory = get_session_factory()
    ctx = default_context(settings)
    log.info("worker_started")
    while not stop.is_set():
        if not process_once(factory, ctx):
            stop.wait(POLL_SECONDS)
    log.info("worker_stopped")


if __name__ == "__main__":
    main()
