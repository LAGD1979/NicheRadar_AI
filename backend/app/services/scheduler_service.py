"""Trabajos programados (M5, spec §9.1): el reloj vive en la aplicación, no en Claude Code.

Cada trabajo es una fila de `scheduled_jobs` con su intervalo y su próxima ejecución en UTC. El
worker llama a `tick` cada pocos segundos: encola los trabajos vencidos como corridas normales
(las ejecuta el mismo worker, con sus reintentos y auditoría) y reprograma. Es idempotente:

- el bloqueo `FOR UPDATE SKIP LOCKED` impide que dos workers encolen el mismo trabajo;
- tras un reinicio o una caída se ejecuta **una** vez, no una por cada intervalo perdido;
- no se encola un trabajo mientras otra corrida del mismo tipo siga en cola o ejecutándose.

Solo hay trabajos baratos y sin costo externo: purga, alertas y revisión del seguimiento con los
datos ya guardados. Lo que gasta cuota o créditos (descubrimiento, demanda, validación) se
sigue iniciando a mano.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.db import models as m
from app.services.research_service import enqueue_run

MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 24 * 30
ACTIVE_RUN_STATUSES = ("QUEUED", "RUNNING")

JOBS: dict[str, dict[str, Any]] = {
    "retention_purge": {
        "label": "Purga de datos caducados",
        "description": "Borra los datos de terceros que pasaron de 29 días y deja registro.",
        "kind": "purge",
        "interval_hours": 24,
        "algorithm_version": "m1-purge-1",
    },
    "alerts_check": {
        "label": "Revisión de alertas",
        "description": (
            "Busca cuotas al límite, datos por caducar, autorizaciones por vencer y fuentes caídas."
        ),
        "kind": "alerts",
        "interval_hours": 6,
        "algorithm_version": "m5-alerts-1",
    },
    "watchlist_recheck": {
        "label": "Revisión del seguimiento",
        "description": (
            "Recalcula con los datos guardados las oportunidades en seguimiento y avisa de cambios."
        ),
        "kind": "watchlist",
        "interval_hours": 168,
        "algorithm_version": "m5-watchlist-1",
    },
}


def ensure_defaults(session: Session, now: datetime) -> None:
    """Crea los trabajos que falten, habilitados y con su primera ejecución ya vencida."""
    existing = set(session.scalars(select(m.ScheduledJob.job_type)))
    for job_type, meta in JOBS.items():
        if job_type not in existing:
            session.add(
                m.ScheduledJob(
                    job_type=job_type,
                    enabled=True,
                    interval_hours=int(meta["interval_hours"]),
                    next_run_at=now,
                    updated_by="system",
                )
            )
    session.flush()


def _view(job: m.ScheduledJob) -> dict[str, Any]:
    meta = JOBS.get(job.job_type, {})
    return {
        "job_type": job.job_type,
        "label": meta.get("label", job.job_type),
        "description": meta.get("description", ""),
        "enabled": job.enabled,
        "interval_hours": job.interval_hours,
        "next_run_at": job.next_run_at.isoformat(),
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "last_run_id": job.last_run_id,
    }


def list_jobs(session: Session, now: datetime) -> list[dict[str, Any]]:
    ensure_defaults(session, now)
    rows = {r.job_type: r for r in session.scalars(select(m.ScheduledJob))}
    out = []
    for job_type in JOBS:
        view = _view(rows[job_type])
        run = (
            session.get(m.ResearchRun, rows[job_type].last_run_id)
            if rows[job_type].last_run_id
            else None
        )
        view["last_status"] = run.status if run else None
        out.append(view)
    return out


def _job(session: Session, job_type: str, now: datetime) -> m.ScheduledJob:
    if job_type not in JOBS:
        raise ProblemError(404, "JOB_NOT_FOUND", "Trabajo programado desconocido")
    ensure_defaults(session, now)
    job = session.get(m.ScheduledJob, job_type)
    assert job is not None
    return job


def update_job(
    session: Session,
    job_type: str,
    *,
    enabled: bool | None,
    interval_hours: int | None,
    by: str,
    now: datetime,
) -> dict[str, Any]:
    job = _job(session, job_type, now)
    if interval_hours is not None:
        if not MIN_INTERVAL_HOURS <= interval_hours <= MAX_INTERVAL_HOURS:
            raise ProblemError(
                422,
                "INVALID_INTERVAL",
                "Intervalo no válido",
                f"Entre {MIN_INTERVAL_HOURS} y {MAX_INTERVAL_HOURS} horas.",
            )
        if interval_hours != job.interval_hours:
            job.interval_hours = interval_hours
            job.next_run_at = min(job.next_run_at, now + timedelta(hours=interval_hours))
    if enabled is not None:
        if enabled and not job.enabled:
            job.next_run_at = now + timedelta(hours=job.interval_hours)
        job.enabled = enabled
    job.updated_by = by
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=None,
            actor=by,
            event_type="SCHEDULED_JOB_CHANGED",
            object_type="scheduled_job",
            object_id=job_type,
            details_redacted_json={"enabled": job.enabled, "interval_hours": job.interval_hours},
        )
    )
    session.flush()
    return _view(job)


def _has_active_run(session: Session, kind: str) -> bool:
    return (
        session.scalars(
            select(m.ResearchRun.id)
            .where(m.ResearchRun.kind == kind, m.ResearchRun.status.in_(ACTIVE_RUN_STATUSES))
            .limit(1)
        ).first()
        is not None
    )


def _enqueue(
    session: Session, settings: Settings, job: m.ScheduledJob, *, actor: str, now: datetime
) -> m.ResearchRun:
    meta = JOBS[job.job_type]
    run = enqueue_run(
        session,
        kind=str(meta["kind"]),
        policy_mode=settings.compliance_mode,
        payload={"scheduled_job": job.job_type},
        params={"scheduled_job": job.job_type, "trigger": actor},
        algorithm_version=str(meta["algorithm_version"]),
        budget={},
        actor=actor,
    )
    job.last_run_at = now
    job.last_run_id = run.id
    return run


def run_now(
    session: Session, settings: Settings, job_type: str, *, by: str, now: datetime
) -> m.ResearchRun:
    """Ejecución manual: no cambia el calendario, pero tampoco se solapa con otra en curso."""
    job = _job(session, job_type, now)
    if _has_active_run(session, str(JOBS[job_type]["kind"])):
        raise ProblemError(
            409, "JOB_ALREADY_RUNNING", "Ya hay una corrida de este trabajo en curso"
        )
    return _enqueue(session, settings, job, actor=by, now=now)


def tick(session: Session, settings: Settings, now: datetime) -> list[str]:
    """Encola los trabajos vencidos. Devuelve los tipos encolados."""
    ensure_defaults(session, now)
    due = session.scalars(
        select(m.ScheduledJob)
        .where(m.ScheduledJob.enabled.is_(True), m.ScheduledJob.next_run_at <= now)
        .order_by(m.ScheduledJob.next_run_at)
        .with_for_update(skip_locked=True)
    ).all()
    enqueued: list[str] = []
    for job in due:
        job.next_run_at = now + timedelta(hours=job.interval_hours)
        if _has_active_run(session, str(JOBS[job.job_type]["kind"])):
            continue  # contrapresión: se salta esta vuelta, la siguiente lo intenta
        _enqueue(session, settings, job, actor="scheduler", now=now)
        enqueued.append(job.job_type)
    session.flush()
    return enqueued
