"""Control de cuota por unidades (spec §9.2). Se reserva antes de cada llamada.

El día de cuota de YouTube empieza a medianoche de Pacific Time (D-22), no UTC.
"""

from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m
from app.providers.base import QuotaExhausted

PROVIDER = "youtube_official"
QUOTA_BUCKET = "youtube_units"
QUOTA_TZ = ZoneInfo("America/Los_Angeles")


def quota_day_start(now: datetime) -> datetime:
    local = now.astimezone(QUOTA_TZ)
    start_local = datetime.combine(local.date(), time.min, tzinfo=QUOTA_TZ)
    return start_local.astimezone(UTC)


def next_quota_reset(now: datetime) -> datetime:
    return quota_day_start(now) + timedelta(days=1)


def units_used_today(session: Session, now: datetime) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(m.ProviderUsage.units), 0)).where(
            m.ProviderUsage.provider == PROVIDER,
            m.ProviderUsage.quota_bucket == QUOTA_BUCKET,
            m.ProviderUsage.started_at >= quota_day_start(now),
        )
    )
    return int(total or 0)


def daily_budget(settings: Settings) -> int:
    """Límite blando: se corta antes del tope real para dejar margen (p. ej. 90 % de 10 000)."""
    return int(settings.youtube_daily_units_limit * settings.youtube_daily_units_soft_pct)


def reserve(
    session: Session,
    settings: Settings,
    *,
    endpoint: str,
    units: int,
    run_id: str | None,
    now: datetime,
) -> None:
    """Registra el consumo previsto. Si no cabe en el presupuesto del día, lanza QuotaExhausted."""
    used = units_used_today(session, now)
    if used + units > daily_budget(settings):
        raise QuotaExhausted(
            f"Presupuesto diario local agotado: {used} de {daily_budget(settings)} unidades usadas."
        )
    session.add(
        m.ProviderUsage(
            id=str(uuid4()),
            run_id=run_id,
            provider=PROVIDER,
            endpoint=endpoint,
            quota_bucket=QUOTA_BUCKET,
            units=units,
            started_at=now,
            status="RESERVED",
        )
    )
    session.flush()


def snapshot(session: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    used = units_used_today(session, now)
    budget = daily_budget(settings)
    return {
        "provider": PROVIDER,
        "quota_bucket": QUOTA_BUCKET,
        "day_start_utc": quota_day_start(now).isoformat(),
        "resets_at_utc": next_quota_reset(now).isoformat(),
        "units_used": used,
        "units_budget_soft": budget,
        "units_limit_hard": settings.youtube_daily_units_limit,
        "units_remaining_soft": max(0, budget - used),
    }
