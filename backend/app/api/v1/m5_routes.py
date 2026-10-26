"""M5: trabajos programados, seguimiento de oportunidades y alertas. Local y de un solo usuario."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services import alerts_service, scheduler_service, watchlist_service

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ACTOR = "local_owner"


# --- trabajos programados ---------------------------------------------------------------------


class JobUpdate(BaseModel):
    enabled: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=scheduler_service.MAX_INTERVAL_HOURS)


@router.get("/scheduler/jobs")
def scheduler_jobs(session: SessionDep) -> list[dict[str, Any]]:
    jobs = scheduler_service.list_jobs(session, datetime.now(UTC))
    session.commit()  # puede haber creado los trabajos por defecto
    return jobs


@router.patch("/scheduler/jobs/{job_type}")
def scheduler_job_update(job_type: str, body: JobUpdate, session: SessionDep) -> dict[str, Any]:
    job = scheduler_service.update_job(
        session,
        job_type,
        enabled=body.enabled,
        interval_hours=body.interval_hours,
        by=ACTOR,
        now=datetime.now(UTC),
    )
    session.commit()
    return job


@router.post("/scheduler/jobs/{job_type}/run", status_code=202)
def scheduler_job_run(job_type: str, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    run = scheduler_service.run_now(session, settings, job_type, by=ACTOR, now=datetime.now(UTC))
    session.commit()
    return {"id": run.id, "kind": run.kind, "status": run.status}


# --- alertas ----------------------------------------------------------------------------------


@router.get("/alerts")
def alerts(session: SessionDep, include_acknowledged: bool = False) -> dict[str, Any]:
    return alerts_service.list_alerts(session, include_acknowledged=include_acknowledged)


@router.post("/alerts/acknowledge-all")
def alerts_acknowledge_all(session: SessionDep) -> dict[str, int]:
    count = alerts_service.acknowledge_all(session, datetime.now(UTC))
    session.commit()
    return {"acknowledged": count}


@router.post("/alerts/{alert_id}/acknowledge")
def alert_acknowledge(alert_id: str, session: SessionDep) -> dict[str, Any]:
    alert = alerts_service.acknowledge(session, alert_id, datetime.now(UTC))
    session.commit()
    return alert


# --- seguimiento ------------------------------------------------------------------------------


class PilotPlan(BaseModel):
    """Plan de piloto escrito por el propietario. Los resultados los mide él en YouTube Studio."""

    hypothesis: str = Field(default="", max_length=1000)
    proposed_videos: list[str] = Field(default_factory=list, max_length=5)
    success_metrics: str = Field(default="", max_length=1000)

    @field_validator("proposed_videos")
    @classmethod
    def _videos(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v.strip()]
        if any(len(v) > 200 for v in cleaned):
            raise ValueError("cada video propuesto admite hasta 200 caracteres")
        return cleaned


class WatchCreate(BaseModel):
    priority: str = "MEDIUM"
    notes: str | None = Field(default=None, max_length=2000)
    review_days: int = Field(default=watchlist_service.DEFAULT_REVIEW_DAYS, ge=1, le=365)


class WatchUpdate(BaseModel):
    priority: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    next_review_at: datetime | None = None
    pilot_plan: PilotPlan | None = None


class WatchReviewed(BaseModel):
    review_days: int = Field(default=watchlist_service.DEFAULT_REVIEW_DAYS, ge=1, le=365)


class WatchRemove(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.get("/watchlist")
def watchlist(session: SessionDep) -> list[dict[str, Any]]:
    return watchlist_service.list_watchlist(session, datetime.now(UTC))


@router.post("/opportunities/{opportunity_id}/watch", status_code=201)
def watch_add(opportunity_id: str, body: WatchCreate, session: SessionDep) -> dict[str, Any]:
    now = datetime.now(UTC)
    watchlist_service.add(
        session,
        opportunity_id,
        priority=body.priority,
        notes=body.notes,
        review_days=body.review_days,
        actor=ACTOR,
        now=now,
    )
    session.commit()
    return watchlist_service.view(session, opportunity_id, now)


@router.patch("/watchlist/{opportunity_id}")
def watch_update(opportunity_id: str, body: WatchUpdate, session: SessionDep) -> dict[str, Any]:
    now = datetime.now(UTC)
    watchlist_service.update(
        session,
        opportunity_id,
        priority=body.priority,
        notes=body.notes,
        next_review_at=body.next_review_at,
        pilot_plan=body.pilot_plan.model_dump() if body.pilot_plan else None,
        actor=ACTOR,
        now=now,
    )
    session.commit()
    return watchlist_service.view(session, opportunity_id, now)


@router.post("/watchlist/{opportunity_id}/reviewed")
def watch_reviewed(opportunity_id: str, body: WatchReviewed, session: SessionDep) -> dict[str, Any]:
    now = datetime.now(UTC)
    watchlist_service.mark_reviewed(
        session, opportunity_id, review_days=body.review_days, actor=ACTOR, now=now
    )
    session.commit()
    return watchlist_service.view(session, opportunity_id, now)


@router.post("/watchlist/{opportunity_id}/remove")
def watch_remove(opportunity_id: str, body: WatchRemove, session: SessionDep) -> dict[str, str]:
    watchlist_service.remove(
        session, opportunity_id, reason=body.reason, actor=ACTOR, now=datetime.now(UTC)
    )
    session.commit()
    return {"status": "removed"}
