"""Worker persistente: toma tareas de `run_tasks` con bloqueo transaccional.

- `FOR UPDATE SKIP LOCKED` evita que dos workers tomen la misma tarea.
- Una tarea RUNNING con arrendamiento vencido (worker caído) se recupera (T21, recuperación).
- Los reintentos son finitos; al agotarlos, la tarea y la corrida quedan FAILED con error.
"""

import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import models as m
from app.db.session import get_session_factory
from app.jobs.handlers import run_demo_research

LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 3
POLL_SECONDS = 2.0
HANDLERS: dict[str, Callable[[Session, str], dict[str, Any]]] = {
    "demo_research": run_demo_research,
}

log = structlog.get_logger("worker")


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
    return task.id, task.run_id, task.task_type


def process_once(factory: sessionmaker[Session]) -> bool:
    """Procesa como máximo una tarea. Devuelve False si no había nada que hacer."""
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        claimed = _claim(session, now)
    if claimed is None:
        return False
    task_id, run_id, task_type = claimed

    try:
        with factory() as session, session.begin():
            result = HANDLERS[task_type](session, run_id)
            task = session.get(m.RunTask, task_id)
            if task is None:
                raise LookupError(f"Tarea desaparecida: {task_id}")
            task.status = "SUCCEEDED"
            task.result_json = result
            task.locked_at = None
        log.info("task_succeeded", task_id=task_id, task_type=task_type)
    except Exception as exc:
        _record_failure(factory, task_id, run_id, type(exc).__name__, now)
    return True


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
                run.errors_json = [*run.errors_json, {"task": task.task_type, "code": error_class}]
            log.error("task_failed", task_id=task_id, error_class=error_class)
        else:
            task.status = "PENDING"
            task.next_attempt_at = now + timedelta(seconds=2**task.attempts)
            log.warning("task_retry_scheduled", task_id=task_id, error_class=error_class)


def main() -> None:
    configure_logging(get_settings().log_level)
    stop = threading.Event()

    def _request_stop(signum: int, _frame: Any) -> None:
        log.info("stop_requested", signal=signum)
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    factory = get_session_factory()
    log.info("worker_started")
    while not stop.is_set():
        if not process_once(factory):
            stop.wait(POLL_SECONDS)
    log.info("worker_stopped")


if __name__ == "__main__":
    main()
