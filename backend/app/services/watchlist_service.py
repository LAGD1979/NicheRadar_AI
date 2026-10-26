"""Seguimiento de oportunidades (M5, spec §8.8): guardar, anotar, revisar y ver qué cambió.

Una oportunidad en seguimiento guarda una **foto** de sus indicadores (`snapshot_json`). La
revisión periódica recalcula con los datos ya guardados, compara con la foto y avisa de los
cambios; la foto solo se renueva cuando una persona marca la oportunidad como revisada, así los
cambios se acumulan hasta que alguien los ve. Las decisiones quedan en `review_actions` (solo se
agregan). Los resultados de un piloto los mide y escribe el propietario: aquí no se inventan.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.db import models as m
from app.services import alerts_service, evaluation_service, replication_service, spanish_service

PRIORITIES = ("LOW", "MEDIUM", "HIGH")
DEFAULT_REVIEW_DAYS = 7
MAX_REVIEW_DAYS = 365
MIN_REMOVE_REASON = 5
CONFIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
CHANGE_KEYS = (
    "confidence",
    "recommendation",
    "independent_channels",
    "replication_state",
    "saturation_state",
    "spanish_demand_state",
    "independent_signals",
    "exact_matches",
    "reviewed_matches",
    "es_verified_videos",
)


def metrics_for(session: Session, opportunity_id: str) -> dict[str, Any]:
    """Indicadores de la última evaluación; sin evaluación, todos desconocidos (no ceros)."""
    ev = evaluation_service.latest_evaluation(session, opportunity_id)
    if ev is None:
        return {key: None for key in CHANGE_KEYS} | {
            "evaluation_version": None,
            "review_share": None,
        }
    international = ev.international_json or {}
    spanish = ev.spanish_json or {}
    verified = spanish.get("es_verified_videos")
    reviewed = spanish.get("reviewed_matches")
    share = (
        round(reviewed / verified, 3)
        if isinstance(verified, int) and verified > 0 and isinstance(reviewed, int)
        else None
    )
    return {
        "evaluation_version": ev.evaluation_version,
        "confidence": ev.confidence,
        "recommendation": ev.recommendation,
        "independent_channels": international.get("independent_channels_observed"),
        "replication_state": international.get("replication_state"),
        "saturation_state": spanish.get("saturation_state"),
        "spanish_demand_state": spanish.get("spanish_demand_state"),
        "independent_signals": (spanish.get("demand_signals") or {}).get("independent_signals"),
        "exact_matches": spanish.get("exact_matches"),
        "reviewed_matches": reviewed,
        "es_verified_videos": verified,
        "review_share": share,
    }


def changes_since(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key, "before": before.get(key), "after": after.get(key)}
        for key in CHANGE_KEYS
        if before.get(key) != after.get(key)
    ]


def _record(
    session: Session,
    opportunity_id: str,
    action: str,
    reason: str | None,
    actor: str,
    now: datetime,
) -> None:
    # La hora se fija aquí (no la de la transacción) para que el orden de las acciones sea exacto.
    session.add(
        m.ReviewAction(
            id=str(uuid4()),
            opportunity_id=opportunity_id,
            action=action,
            reason=reason,
            actor=actor,
            created_at=now,
        )
    )


def _opportunity(session: Session, opportunity_id: str) -> m.Opportunity:
    opportunity = session.get(m.Opportunity, opportunity_id)
    if opportunity is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    return opportunity


def _entry(session: Session, opportunity_id: str) -> m.Watchlist:
    entry = session.scalars(
        select(m.Watchlist).where(m.Watchlist.opportunity_id == opportunity_id)
    ).first()
    if entry is None:
        raise ProblemError(404, "NOT_IN_WATCHLIST", "La oportunidad no está en seguimiento")
    return entry


def _check_priority(priority: str) -> None:
    if priority not in PRIORITIES:
        raise ProblemError(422, "INVALID_PRIORITY", "Prioridad no válida")


def _review_date(days: int, now: datetime) -> datetime:
    if not 1 <= days <= MAX_REVIEW_DAYS:
        raise ProblemError(
            422,
            "INVALID_REVIEW_DAYS",
            "Días de revisión no válidos",
            f"Entre 1 y {MAX_REVIEW_DAYS}.",
        )
    return now + timedelta(days=days)


def add(
    session: Session,
    opportunity_id: str,
    *,
    priority: str,
    notes: str | None,
    review_days: int,
    actor: str,
    now: datetime,
) -> m.Watchlist:
    _opportunity(session, opportunity_id)
    _check_priority(priority)
    existing = session.scalars(
        select(m.Watchlist).where(m.Watchlist.opportunity_id == opportunity_id)
    ).first()
    if existing is not None:
        raise ProblemError(409, "ALREADY_IN_WATCHLIST", "La oportunidad ya está en seguimiento")
    entry = m.Watchlist(
        id=str(uuid4()),
        opportunity_id=opportunity_id,
        priority=priority,
        next_review_at=_review_date(review_days, now),
        notes=(notes or "").strip() or None,
        pilot_plan_json={},
        snapshot_json=metrics_for(session, opportunity_id),
        snapshot_at=now,
    )
    session.add(entry)
    _record(session, opportunity_id, "WATCH", entry.notes, actor, now)
    session.flush()
    return entry


def update(
    session: Session,
    opportunity_id: str,
    *,
    priority: str | None,
    notes: str | None,
    next_review_at: datetime | None,
    pilot_plan: dict[str, Any] | None,
    actor: str,
    now: datetime,
) -> m.Watchlist:
    entry = _entry(session, opportunity_id)
    if priority is not None:
        _check_priority(priority)
        entry.priority = priority
    if notes is not None:
        entry.notes = notes.strip() or None
    if next_review_at is not None:
        entry.next_review_at = next_review_at
    if pilot_plan is not None:
        entry.pilot_plan_json = pilot_plan
    entry.updated_at = now
    _record(
        session,
        opportunity_id,
        "UPDATE",
        "Notas, prioridad o plan de piloto actualizados",
        actor,
        now,
    )
    session.flush()
    return entry


def mark_reviewed(
    session: Session, opportunity_id: str, *, review_days: int, actor: str, now: datetime
) -> m.Watchlist:
    """La persona vio los cambios: se renueva la foto y se programa la siguiente revisión."""
    entry = _entry(session, opportunity_id)
    entry.snapshot_json = metrics_for(session, opportunity_id)
    entry.snapshot_at = now
    entry.next_review_at = _review_date(review_days, now)
    entry.updated_at = now
    _record(session, opportunity_id, "REVIEWED", None, actor, now)
    session.flush()
    return entry


def remove(
    session: Session, opportunity_id: str, *, reason: str, actor: str, now: datetime
) -> None:
    entry = _entry(session, opportunity_id)
    if len(reason.strip()) < MIN_REMOVE_REASON:
        raise ProblemError(
            422,
            "REASON_REQUIRED",
            "Indique el motivo",
            f"Escriba al menos {MIN_REMOVE_REASON} caracteres.",
        )
    session.delete(entry)
    _record(session, opportunity_id, "UNWATCH", reason.strip(), actor, now)
    session.flush()


def _view(session: Session, entry: m.Watchlist, now: datetime) -> dict[str, Any]:
    opportunity = session.get(m.Opportunity, entry.opportunity_id)
    assert opportunity is not None
    niche = session.get(m.Niche, opportunity.niche_id)
    fmt = session.get(m.Format, opportunity.format_id)
    last = session.scalars(
        select(m.ReviewAction)
        .where(m.ReviewAction.opportunity_id == entry.opportunity_id)
        .order_by(m.ReviewAction.created_at.desc())
    ).first()
    current = metrics_for(session, entry.opportunity_id)
    open_alerts = session.scalars(
        select(m.Alert.id).where(
            m.Alert.opportunity_id == entry.opportunity_id, m.Alert.acknowledged_at.is_(None)
        )
    ).all()
    return {
        "opportunity_id": entry.opportunity_id,
        "niche": niche.canonical_name_es if niche else None,
        "format": fmt.canonical_name_es if fmt else None,
        "video_type": opportunity.video_type,
        "status": opportunity.status,
        "priority": entry.priority,
        "notes": entry.notes,
        "pilot_plan": entry.pilot_plan_json,
        "next_review_at": entry.next_review_at.isoformat(),
        "review_overdue": entry.next_review_at <= now,
        "snapshot_at": entry.snapshot_at.isoformat(),
        "current": current,
        "changes": changes_since(entry.snapshot_json, current),
        "open_alerts": len(open_alerts),
        "last_action": (
            {
                "action": last.action,
                "reason": last.reason,
                "actor": last.actor,
                "created_at": last.created_at.isoformat(),
            }
            if last
            else None
        ),
    }


def view(session: Session, opportunity_id: str, now: datetime) -> dict[str, Any]:
    return _view(session, _entry(session, opportunity_id), now)


def list_watchlist(session: Session, now: datetime) -> list[dict[str, Any]]:
    entries = session.scalars(select(m.Watchlist).order_by(m.Watchlist.next_review_at)).all()
    order = {p: i for i, p in enumerate(reversed(PRIORITIES))}
    views = [_view(session, e, now) for e in entries]
    return sorted(views, key=lambda v: (order.get(v["priority"], 9), v["next_review_at"]))


# --- revisión periódica -----------------------------------------------------------------------


def recheck(session: Session, settings: Settings, now: datetime) -> dict[str, int]:
    """Recalcula con los datos guardados cada oportunidad en seguimiento y avisa de cambios.

    No llama a ningún proveedor ni gasta saldo. Un cambio ya avisado no se repite (la clave de la
    alerta incluye la versión de la evaluación).
    """
    entries = session.scalars(select(m.Watchlist)).all()
    created = 0
    for entry in entries:
        try:
            replication_service.refresh(session, settings, entry.opportunity_id, now)
        except LookupError:
            continue
        created += _alerts_for(session, entry, now)
    return {"reviewed": len(entries), "alerts_created": created}


def _increase(before: Any, after: Any, *, had_evaluation: bool) -> bool:
    """¿Subió el conteo? Si ya existía una evaluación, un conteo ausente equivale a cero."""
    if before is None and had_evaluation:
        before = 0
    return isinstance(before, int) and isinstance(after, int) and after > before


def _alerts_for(session: Session, entry: m.Watchlist, now: datetime) -> int:
    opp = entry.opportunity_id
    before, after = entry.snapshot_json, metrics_for(session, opp)
    known = before.get("evaluation_version") is not None
    version = after.get("evaluation_version")
    if version is None:
        return 0
    name = session.scalar(
        select(m.Niche.canonical_name_es)
        .join(m.Opportunity, m.Opportunity.niche_id == m.Niche.id)
        .where(m.Opportunity.id == opp)
    )
    label = f"«{name}»" if name else "La oportunidad"
    created = 0

    def alert(alert_type: str, severity: str, message: str) -> None:
        nonlocal created
        created += alerts_service.raise_alert(
            session,
            alert_type=alert_type,
            severity=severity,
            message=message,
            dedupe_key=f"{alert_type}:{opp}:v{version}",
            now=now,
            opportunity_id=opp,
            details={"before": before, "after": after},
        )

    if _increase(
        before.get("independent_channels"), after.get("independent_channels"), had_evaluation=known
    ):
        alert(
            "NEW_INTERNATIONAL_PATTERN",
            "INFO",
            f"{label}: hay más canales independientes con el formato "
            f"({before.get('independent_channels') or 0} → {after['independent_channels']}).",
        )
    if _increase(
        before.get("independent_signals"), after.get("independent_signals"), had_evaluation=known
    ):
        alert(
            "SPANISH_DEMAND_SIGNAL",
            "INFO",
            f"{label}: hay una señal de demanda en español más "
            f"({before.get('independent_signals') or 0} → {after['independent_signals']}).",
        )
    rank_before = CONFIDENCE_RANK.get(str(before.get("confidence")), 0)
    rank_after = CONFIDENCE_RANK.get(str(after.get("confidence")), 0)
    if rank_after > rank_before > 0:
        alert(
            "OPPORTUNITY_CONFIDENCE_UPGRADE",
            "INFO",
            f"{label}: la confianza subió de {before['confidence']} a {after['confidence']}.",
        )
    # Solo es una comparación confiable si en ambos momentos se había revisado lo suficiente.
    minimum = spanish_service.min_review_share()
    comparable = all(
        isinstance(s.get("review_share"), float | int) and s["review_share"] >= minimum
        for s in (before, after)
    )
    if comparable and _increase(
        before.get("exact_matches"), after.get("exact_matches"), had_evaluation=known
    ):
        alert(
            "SPANISH_COMPETITION_INCREASE",
            "WARNING",
            f"{label}: aumentaron los competidores exactos en español "
            f"({before.get('exact_matches') or 0} → {after['exact_matches']}).",
        )
    return created
