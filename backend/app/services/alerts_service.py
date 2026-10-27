"""Alertas dentro de la aplicación (M5, spec §9.4).

Una alerta nace solo de un hecho guardado y medible; nunca de una suposición. Cada una lleva una
`dedupe_key` que identifica el hecho (por ejemplo «cuota de vidIQ, 2026-10-27»), de modo que una
revisión repetida no la duplica. Una persona las marca como vistas; no se borran.

Alertas del sistema (`check_system`): `QUOTA_WARNING`, `DATA_STALE`, `POLICY_REVIEW_REQUIRED` y
`SOURCE_UNAVAILABLE`. Alertas de una oportunidad en seguimiento (`watchlist_service`):
`NEW_INTERNATIONAL_PATTERN`, `SPANISH_DEMAND_SIGNAL`, `OPPORTUNITY_CONFIDENCE_UPGRADE` y
`SPANISH_COMPETITION_INCREASE`.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.db import models as m
from app.services import ai_budget_service, demand_service, quota_service, vidiq_service

QUOTA_WARN_SHARE = 0.8
STALE_WINDOW_DAYS = 3
POLICY_WINDOW_DAYS = 30
SOURCE_WINDOW_HOURS = 24
SEVERITIES = ("INFO", "WARNING", "CRITICAL")


def raise_alert(
    session: Session,
    *,
    alert_type: str,
    severity: str,
    message: str,
    dedupe_key: str,
    now: datetime,
    opportunity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    """Crea la alerta si ese hecho aún no la tiene. Devuelve si se creó."""
    exists = session.scalars(
        select(m.Alert.id).where(m.Alert.dedupe_key == dedupe_key).limit(1)
    ).first()
    if exists is not None:
        return False
    session.add(
        m.Alert(
            id=str(uuid4()),
            alert_type=alert_type,
            severity=severity,
            opportunity_id=opportunity_id,
            message=message,
            details_json=details or {},
            dedupe_key=dedupe_key,
            created_at=now,
        )
    )
    session.flush()
    return True


def _quota_alerts(session: Session, settings: Settings, now: datetime) -> int:
    day = now.date().isoformat()
    month = now.strftime("%Y-%m")
    youtube = quota_service.snapshot(session, settings, now)
    vidiq = vidiq_service.snapshot(session, settings, now)
    hasdata = demand_service.hasdata_snapshot(session, settings, now)
    ai = ai_budget_service.snapshot(session, settings, now)
    checks = (
        (
            "IA",
            f"ai:{day}",
            ai["tokens_used"],
            ai["tokens_daily_limit"],
            "tokens",
            "hoy",
        ),
        (
            "YouTube",
            f"youtube:{day}",
            youtube["units_used"],
            youtube["units_budget_soft"],
            "unidades",
            "hoy",
        ),
        (
            "vidIQ",
            f"vidiq:{day}",
            vidiq["credits_used"],
            vidiq["credits_daily_limit"],
            "créditos",
            "hoy",
        ),
        (
            "HasData",
            f"hasdata:{month}",
            hasdata["calls_month_used"],
            hasdata["calls_monthly_limit"],
            "consultas",
            "este mes",
        ),
    )
    created = 0
    for name, key, used, limit, unit, period in checks:
        if limit <= 0 or used / limit < QUOTA_WARN_SHARE:
            continue
        exhausted = used >= limit
        created += raise_alert(
            session,
            alert_type="QUOTA_WARNING",
            severity="CRITICAL" if exhausted else "WARNING",
            message=(
                f"{name}: {'se agotó' if exhausted else 'queda poco de'} el tope de {period} "
                f"({used} de {limit} {unit})."
            ),
            dedupe_key=f"quota:{key}:{'full' if exhausted else 'warn'}",
            now=now,
            details={"provider": name, "used": used, "limit": limit},
        )
    return created


def _stale_alert(session: Session, now: datetime) -> int:
    horizon = now + timedelta(days=STALE_WINDOW_DAYS)
    videos = session.scalar(
        select(func.count())
        .select_from(m.Video)
        .where(
            m.Video.retention_deadline.is_not(None),
            m.Video.retention_deadline >= now,
            m.Video.retention_deadline < horizon,
            m.Video.owner_authorized.is_(False),
            m.Video.availability != "EXPIRED",
        )
    )
    observations = session.scalar(
        select(func.count())
        .select_from(m.DemandObservation)
        .where(
            m.DemandObservation.retention_deadline.is_not(None),
            m.DemandObservation.retention_deadline >= now,
            m.DemandObservation.retention_deadline < horizon,
            m.DemandObservation.availability != "EXPIRED",
        )
    )
    videos, observations = int(videos or 0), int(observations or 0)
    if videos + observations == 0:
        return 0
    return raise_alert(
        session,
        alert_type="DATA_STALE",
        severity="WARNING",
        message=(
            f"En los próximos {STALE_WINDOW_DAYS} días caducan {videos} videos y {observations} "
            "mediciones de demanda de terceros. Refrésquelos o se purgarán (quedarán vacíos)."
        ),
        dedupe_key=f"stale:{now.date().isoformat()}",
        now=now,
        details={"videos": videos, "demand_observations": observations},
    )


def _policy_alerts(session: Session, now: datetime) -> int:
    horizon = now + timedelta(days=POLICY_WINDOW_DAYS)
    approvals = session.scalars(
        select(m.PolicyApproval).where(
            m.PolicyApproval.status == "ACTIVE",
            m.PolicyApproval.expires_at.is_not(None),
            m.PolicyApproval.expires_at < horizon,
        )
    ).all()
    created = 0
    for approval in approvals:
        assert approval.expires_at is not None
        expired = approval.expires_at < now
        when = approval.expires_at.date().isoformat()
        created += raise_alert(
            session,
            alert_type="POLICY_REVIEW_REQUIRED",
            severity="CRITICAL" if expired else "WARNING",
            message=(
                f"La autorización de «{approval.capability}» ({approval.provider}) "
                f"{'venció' if expired else 'vence'} el {when}. "
                + ("Esa función quedó bloqueada." if expired else "Renuévela antes de perderla.")
            ),
            dedupe_key=f"policy:{approval.id}:{'expired' if expired else 'soon'}",
            now=now,
            details={"capability": approval.capability, "provider": approval.provider},
        )
    return created


def _source_alerts(session: Session, now: datetime) -> int:
    since = now - timedelta(hours=SOURCE_WINDOW_HOURS)
    runs = session.scalars(
        select(m.ResearchRun).where(
            m.ResearchRun.created_at >= since,
            m.ResearchRun.status.in_(("FAILED", "PARTIAL")),
        )
    ).all()
    created = 0
    for run in runs:
        auth = [e for e in run.errors_json if e.get("code") == "AUTH_ERROR"]
        if not auth:
            continue
        created += raise_alert(
            session,
            alert_type="SOURCE_UNAVAILABLE",
            severity="CRITICAL",
            message=(
                f"Una corrida de «{run.kind}» fue rechazada por una credencial: "
                f"{str(auth[0].get('detail', ''))[:160]}. Revise la clave y reinicie."
            ),
            dedupe_key=f"source:{run.id}",
            now=now,
            details={"run_id": run.id, "kind": run.kind},
        )
    return created


def _backup_alerts(session: Session, now: datetime) -> int:
    """Avisa si el último backup falló o si el trabajo lleva el doble de su intervalo sin uno."""
    job = session.get(m.ScheduledJob, "db_backup")
    if job is None or not job.enabled:
        return 0
    runs = session.scalars(
        select(m.ResearchRun)
        .where(m.ResearchRun.kind == "backup")
        .order_by(m.ResearchRun.created_at.desc())
        .limit(1)
    ).all()
    last = runs[0] if runs else None
    if last is not None and last.status == "FAILED":
        detail = str(last.errors_json[0].get("detail", "")) if last.errors_json else ""
        return raise_alert(
            session,
            alert_type="BACKUP_FAILED",
            severity="CRITICAL",
            message=f"El último backup de la base falló: {detail[:200]}",
            dedupe_key=f"backup-failed:{last.id}",
            now=now,
            details={"run_id": last.id},
        )
    done = session.scalar(
        select(func.max(m.ResearchRun.finished_at)).where(
            m.ResearchRun.kind == "backup", m.ResearchRun.status == "COMPLETED"
        )
    )
    if done is None or now - done <= timedelta(hours=2 * job.interval_hours):
        return 0
    return raise_alert(
        session,
        alert_type="BACKUP_STALE",
        severity="WARNING",
        message=f"Hace más de {2 * job.interval_hours} horas que no hay un backup correcto.",
        dedupe_key=f"backup-stale:{done.date().isoformat()}",
        now=now,
        details={"last_ok_at": done.isoformat()},
    )


def check_system(session: Session, settings: Settings, now: datetime) -> dict[str, int]:
    """Alertas que no dependen de una oportunidad. Solo lee datos guardados."""
    return {
        "quota": _quota_alerts(session, settings, now),
        "stale": _stale_alert(session, now),
        "policy": _policy_alerts(session, now),
        "source": _source_alerts(session, now),
        "backup": _backup_alerts(session, now),
    }


# --- lectura y acuse ---------------------------------------------------------------------------


def _view(alert: m.Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "opportunity_id": alert.opportunity_id,
        "message": alert.message,
        "details": alert.details_json,
        "created_at": alert.created_at.isoformat(),
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
    }


def list_alerts(
    session: Session, *, include_acknowledged: bool, limit: int = 100
) -> dict[str, Any]:
    stmt = select(m.Alert).order_by(m.Alert.created_at.desc()).limit(limit)
    if not include_acknowledged:
        stmt = stmt.where(m.Alert.acknowledged_at.is_(None))
    open_count = session.scalar(
        select(func.count()).select_from(m.Alert).where(m.Alert.acknowledged_at.is_(None))
    )
    critical = session.scalar(
        select(func.count())
        .select_from(m.Alert)
        .where(m.Alert.acknowledged_at.is_(None), m.Alert.severity == "CRITICAL")
    )
    return {
        "open": int(open_count or 0),
        "critical": int(critical or 0),
        "items": [_view(a) for a in session.scalars(stmt)],
    }


def acknowledge(session: Session, alert_id: str, now: datetime) -> dict[str, Any]:
    alert = session.get(m.Alert, alert_id)
    if alert is None:
        raise ProblemError(404, "ALERT_NOT_FOUND", "Alerta no encontrada")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = now
    session.flush()
    return _view(alert)


def acknowledge_all(session: Session, now: datetime) -> int:
    rows = session.scalars(select(m.Alert).where(m.Alert.acknowledged_at.is_(None))).all()
    for alert in rows:
        alert.acknowledged_at = now
    session.flush()
    return len(rows)
