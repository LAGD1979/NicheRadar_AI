"""Descubrimiento de outliers con vidIQ (D-57).

- Presupuesto de créditos local: tope diario y tope por corrida. Se reserva antes de cada llamada.
- Los videos se guardan como `PROVIDER` con la misma caducidad de 29 días que los de YouTube.
- Si el video o el canal ya existen con otra procedencia (p. ej. YouTube oficial), no se
  sobrescriben: solo se añaden las métricas de vidIQ bajo la clave `vidiq`.
- El idioma del título que filtra vidIQ no es idioma verificado: queda UNKNOWN.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m
from app.providers.base import (
    ChannelRecord,
    InvalidRequest,
    ProviderAuthError,
    ProviderUnavailable,
    QuotaExhausted,
    VideoRecord,
)
from app.providers.vidiq_mcp import OutlierParams, OutlierVideo
from app.services.ingestion_service import upsert_channel, upsert_video

PROVIDER = "vidiq_api"
QUOTA_BUCKET = "vidiq_credits"
ENDPOINT = "outliers"


class OutlierSource(Protocol):
    def outliers(self, params: OutlierParams) -> tuple[list[OutlierVideo], int]: ...


@dataclass(frozen=True)
class OutlierSearch:
    params: OutlierParams

    @property
    def key(self) -> str:
        return json.dumps(self.params.to_arguments(), sort_keys=True, separators=(",", ":"))


@dataclass
class VidIQOutcome:
    completed: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "COMPLETED"
    calls: int = 0
    credits: int = 0
    videos_new: int = 0
    videos_enriched: int = 0
    skipped_records: int = 0


def day_start(now: datetime) -> datetime:
    """Día UTC. El saldo del plan de vidIQ no depende de la zona horaria de YouTube."""
    return datetime.combine(now.astimezone(UTC).date(), time.min, tzinfo=UTC)


def credits_used_today(session: Session, now: datetime) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(m.ProviderUsage.units), 0)).where(
            m.ProviderUsage.provider == PROVIDER,
            m.ProviderUsage.quota_bucket == QUOTA_BUCKET,
            m.ProviderUsage.started_at >= day_start(now),
        )
    )
    return int(total or 0)


def reserve(
    session: Session, settings: Settings, *, credits: int, run_id: str | None, now: datetime
) -> None:
    used = credits_used_today(session, now)
    if used + credits > settings.vidiq_daily_credit_limit:
        raise QuotaExhausted(
            f"Tope diario local de créditos vidIQ: {used} de {settings.vidiq_daily_credit_limit}."
        )
    session.add(
        m.ProviderUsage(
            id=str(uuid4()),
            run_id=run_id,
            provider=PROVIDER,
            endpoint=ENDPOINT,
            quota_bucket=QUOTA_BUCKET,
            units=credits,
            started_at=now,
            status="RESERVED",
        )
    )
    session.flush()


def snapshot(session: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    used = credits_used_today(session, now)
    return {
        "provider": PROVIDER,
        "quota_bucket": QUOTA_BUCKET,
        "day_start_utc": day_start(now).isoformat(),
        "credits_used": used,
        "credits_daily_limit": settings.vidiq_daily_credit_limit,
        "credits_remaining": max(0, settings.vidiq_daily_credit_limit - used),
    }


def _metrics(
    item: OutlierVideo, search: OutlierSearch, run_id: str, now: datetime
) -> dict[str, Any]:
    return {
        "breakout_score": item.breakout_score,
        "views_per_hour": item.views_per_hour,
        "engagement_rate": item.engagement_rate,
        "trend_categories": list(item.trend_categories),
        "ai_labeled": item.ai_labeled,
        "channel_country": item.channel_country,
        "title_language_filter": search.params.language,
        "run_id": run_id,
        "observed_at": now.isoformat(),
    }


def _store(
    session: Session,
    settings: Settings,
    item: OutlierVideo,
    search: OutlierSearch,
    *,
    run_id: str,
    now: datetime,
    outcome: VidIQOutcome,
) -> None:
    video = session.scalars(
        select(m.Video).where(m.Video.youtube_video_id == item.youtube_video_id)
    ).first()
    if video is not None and video.provider != PROVIDER:
        # Procedencia distinta (p. ej. YouTube oficial): se conserva y solo se añade vidIQ aparte.
        video.provider_metrics = {
            **(video.provider_metrics or {}),
            "vidiq": _metrics(item, search, run_id, now),
        }
        outcome.videos_enriched += 1
        session.flush()
        return
    channel = session.scalars(
        select(m.Channel).where(m.Channel.youtube_channel_id == item.youtube_channel_id)
    ).first()
    if channel is None or channel.provider == PROVIDER:
        channel = upsert_channel(
            session,
            ChannelRecord(
                youtube_channel_id=item.youtube_channel_id,
                title=item.channel_title,
                subscriber_count=item.subscriber_count,
                hidden_subscribers=item.subscriber_count is None,
                uploads_playlist_id=None,
                country=item.channel_country,
            ),
            run_id=run_id,
            now=now,
            settings=settings,
            source_data_type="PROVIDER",
            provider=PROVIDER,
        )
    is_new = video is None
    stored = upsert_video(
        session,
        VideoRecord(
            youtube_video_id=item.youtube_video_id,
            youtube_channel_id=item.youtube_channel_id,
            title=item.title,
            published_at=item.published_at,
            duration_iso=None if item.duration_seconds is None else f"PT{item.duration_seconds}S",
            default_language=None,
            default_audio_language=None,
            view_count=item.view_count,
            live_broadcast="none",
        ),
        channel,
        run_id=run_id,
        now=now,
        settings=settings,
        source_data_type="PROVIDER",
        provider=PROVIDER,
    )
    stored.provider_metrics = {"vidiq": _metrics(item, search, run_id, now)}
    if is_new:
        outcome.videos_new += 1
    else:
        outcome.videos_enriched += 1


def run_outlier_discovery(
    session: Session,
    source: OutlierSource,
    settings: Settings,
    *,
    run_id: str,
    searches: list[OutlierSearch],
    completed_keys: set[str],
    max_calls: int,
    now: datetime,
) -> VidIQOutcome:
    """Ejecuta las búsquedas pendientes. Un tope agotado pausa la corrida y guarda el progreso."""
    result = VidIQOutcome(completed=sorted(completed_keys))
    for search in searches:
        if search.key in completed_keys:
            continue
        if result.calls >= max_calls:
            result.outcome = "PARTIAL"
            result.errors.append(
                {"code": "BUDGET_CALLS", "detail": "Presupuesto de consultas agotado."}
            )
            break
        try:
            reserve(
                session, settings, credits=settings.vidiq_credits_per_call, run_id=run_id, now=now
            )
            items, skipped = source.outliers(search.params)
        except QuotaExhausted as exc:
            result.outcome = "PAUSED_QUOTA"
            result.errors.append({"code": "PAUSED_QUOTA", "detail": str(exc)})
            break
        except ProviderAuthError as exc:
            result.outcome = "FAILED"
            result.errors.append({"code": "AUTH_ERROR", "detail": str(exc)})
            break
        except (ProviderUnavailable, InvalidRequest) as exc:
            result.outcome = "PARTIAL"
            result.calls += 1
            result.credits += settings.vidiq_credits_per_call
            result.errors.append({"code": exc.code, "detail": str(exc)})
            continue
        result.calls += 1
        result.credits += settings.vidiq_credits_per_call
        result.skipped_records += skipped
        for item in items:
            _store(session, settings, item, search, run_id=run_id, now=now, outcome=result)
        result.completed.append(search.key)
        completed_keys.add(search.key)
    result.completed = sorted(set(result.completed))
    if result.skipped_records:
        result.errors.append(
            {
                "code": "RECORDS_SKIPPED",
                "detail": f"{result.skipped_records} registros descartados por formato inválido.",
            }
        )
        if result.outcome == "COMPLETED":
            result.outcome = "PARTIAL"
    return result
