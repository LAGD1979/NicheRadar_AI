"""Ingesta desde YouTube Data API: descubrimiento por ventanas e idiomas, enriquecimiento,
deduplicación y coincidencias (spec §3.2, §3.3, §5.2, §9).

Cada escritura es idempotente por `youtube_video_id` / `youtube_channel_id` (T01).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m
from app.domain.classification import (
    classify_language,
    classify_video_type,
    parse_iso_duration,
)
from app.domain.rules import subscriber_band
from app.providers.base import (
    ChannelRecord,
    InvalidRequest,
    ProviderAuthError,
    ProviderUnavailable,
    QuotaExhausted,
    SearchHit,
    SearchParams,
    VideoRecord,
)
from app.services import quota_service

PROVIDER = "youtube_official"
SEARCH_UNITS = 100
BATCH = 50
WINDOWS: dict[str, tuple[int, int]] = {"0-7": (0, 7), "8-30": (8, 30), "31-90": (31, 90)}


class DiscoverySource(Protocol):
    """Lo que necesita la ingesta. El cliente real y los falsos de prueba lo implementan."""

    def search(self, params: SearchParams) -> tuple[list[SearchHit], str | None]: ...
    def videos(self, ids: list[str]) -> list[VideoRecord]: ...
    def channels(self, ids: list[str]) -> list[ChannelRecord]: ...
    def uploads(
        self, playlist_id: str, page_token: str | None = None
    ) -> tuple[list[str], str | None]: ...


def rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_provider_datetime(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)


def window_bounds(window: str, now: datetime) -> tuple[str, str | None]:
    if window not in WINDOWS:
        raise ValueError(f"Ventana desconocida: {window}")
    min_days, max_days = WINDOWS[window]
    after = rfc3339(now - timedelta(days=max_days))
    before = rfc3339(now - timedelta(days=min_days)) if min_days > 0 else None
    return after, before


def retention_deadline(settings: Settings, now: datetime) -> datetime:
    return now + timedelta(days=settings.unauthorized_cache_days)


def upsert_channel(
    session: Session,
    rec: ChannelRecord,
    *,
    run_id: str | None,
    now: datetime,
    settings: Settings,
    source_data_type: str,
    provider: str = PROVIDER,
) -> m.Channel:
    channel = session.scalars(
        select(m.Channel).where(m.Channel.youtube_channel_id == rec.youtube_channel_id)
    ).first()
    if channel is None:
        channel = m.Channel(id=str(uuid4()), youtube_channel_id=rec.youtube_channel_id)
        session.add(channel)
    channel.title_current = rec.title[:200]
    channel.subscriber_count = rec.subscriber_count  # None = oculto, 0 = real
    channel.subscriber_band = subscriber_band(rec.subscriber_count)
    channel.language_state = channel.language_state or "UNKNOWN"
    channel.region_declared = rec.country
    channel.uploads_playlist_id = rec.uploads_playlist_id
    channel.provider = provider
    channel.observed_at = now
    channel.run_id = run_id
    channel.source_data_type = source_data_type
    channel.owner_authorized = False
    channel.retention_deadline = retention_deadline(settings, now)
    channel.last_refreshed_at = now
    session.flush()
    return channel


def upsert_video(
    session: Session,
    rec: VideoRecord,
    channel: m.Channel,
    *,
    run_id: str | None,
    now: datetime,
    settings: Settings,
    source_data_type: str,
    provider: str = PROVIDER,
) -> m.Video:
    video = session.scalars(
        select(m.Video).where(m.Video.youtube_video_id == rec.youtube_video_id)
    ).first()
    if video is None:
        video = m.Video(id=str(uuid4()), youtube_video_id=rec.youtube_video_id)
        session.add(video)
    duration = parse_iso_duration(rec.duration_iso)
    language = classify_language(rec.default_audio_language, rec.default_language)
    kind = classify_video_type(duration, rec.live_broadcast)
    video.channel_id = channel.id
    video.title = rec.title[:300]
    video.published_at = parse_provider_datetime(rec.published_at)
    video.duration_seconds = duration
    video.video_type = kind.video_type
    video.video_type_evidence = kind.evidence[:200]
    video.language_state = language.state
    video.language_confidence = language.confidence
    video.view_count = rec.view_count
    video.url = f"https://www.youtube.com/watch?v={rec.youtube_video_id}"
    video.provider = provider
    video.observed_at = now
    video.run_id = run_id
    video.source_data_type = source_data_type
    video.availability = "AVAILABLE"
    video.owner_authorized = False
    video.retention_deadline = retention_deadline(settings, now)
    video.last_refreshed_at = now
    session.flush()
    return video


def enrich_and_store(
    session: Session,
    source: DiscoverySource,
    video_ids: Sequence[str],
    *,
    run_id: str | None,
    now: datetime,
    settings: Settings,
    source_data_type: str = "OFFICIAL",
) -> dict[str, m.Video]:
    """Obtiene videos y canales por lotes y los guarda. Devuelve los videos por ID de YouTube."""
    unique_ids = list(dict.fromkeys(video_ids))
    if not unique_ids:
        return {}
    quota_service.reserve(
        session,
        settings,
        endpoint="videos",
        units=math.ceil(len(unique_ids) / BATCH),
        run_id=run_id,
        now=now,
    )
    records = source.videos(unique_ids)
    channel_ids = list(dict.fromkeys(r.youtube_channel_id for r in records))
    quota_service.reserve(
        session,
        settings,
        endpoint="channels",
        units=math.ceil(len(channel_ids) / BATCH),
        run_id=run_id,
        now=now,
    )
    channel_records = {c.youtube_channel_id: c for c in source.channels(channel_ids)}
    channels: dict[str, m.Channel] = {}
    for cid in channel_ids:
        channel_rec = channel_records.get(cid)
        if channel_rec is None:
            continue  # canal no devuelto por la API: no se inventa
        channels[cid] = upsert_channel(
            session,
            channel_rec,
            run_id=run_id,
            now=now,
            settings=settings,
            source_data_type=source_data_type,
        )
    stored: dict[str, m.Video] = {}
    for video_rec in records:
        channel = channels.get(video_rec.youtube_channel_id)
        if channel is None:
            continue
        stored[video_rec.youtube_video_id] = upsert_video(
            session,
            video_rec,
            channel,
            run_id=run_id,
            now=now,
            settings=settings,
            source_data_type=source_data_type,
        )
    return stored


@dataclass(frozen=True)
class QueryPlan:
    language: str
    query: str
    window: str
    region: str | None = None

    @property
    def key(self) -> str:
        return f"{self.language}|{self.window}|{self.region or ''}|{self.query}"


@dataclass
class DiscoveryOutcome:
    outcome: str = "COMPLETED"  # COMPLETED | PARTIAL | PAUSED_QUOTA | FAILED
    completed: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    searches: int = 0
    per_language: dict[str, dict[str, int]] = field(default_factory=dict)


def run_discovery(
    session: Session,
    source: DiscoverySource,
    settings: Settings,
    *,
    run_id: str,
    plans: list[QueryPlan],
    completed_keys: set[str],
    max_search_calls: int,
    pages_per_query: int,
    now: datetime,
) -> DiscoveryOutcome:
    """Ejecuta consultas pendientes en orden. Al agotar la cuota se detiene y guarda el progreso."""
    result = DiscoveryOutcome(completed=sorted(completed_keys))
    for plan in plans:
        if plan.key in completed_keys:
            continue
        if result.searches >= max_search_calls:
            result.outcome = "PARTIAL"
            result.errors.append(
                {"code": "BUDGET_SEARCH_CALLS", "detail": "Presupuesto de búsquedas agotado."}
            )
            break
        try:
            _run_one_query(session, source, settings, run_id, plan, pages_per_query, now, result)
        except QuotaExhausted as exc:
            result.outcome = "PAUSED_QUOTA"
            result.errors.append({"code": "PAUSED_QUOTA", "detail": str(exc)})
            break
        except ProviderAuthError as exc:
            result.outcome = "FAILED"
            result.errors.append({"code": "AUTH_ERROR", "detail": str(exc)})
            break
        except (ProviderUnavailable, InvalidRequest) as exc:
            # Un fallo de una consulta no interrumpe las demás (spec §9.3).
            result.outcome = "PARTIAL"
            result.errors.append(
                {"code": exc.code, "detail": f"{plan.language} · {plan.window}: {exc}"}
            )
            session.add(
                _query_row(run_id, plan, now, status="ERROR", count=0, pages=0, warnings=[str(exc)])
            )
            session.flush()
    return result


def _run_one_query(
    session: Session,
    source: DiscoverySource,
    settings: Settings,
    run_id: str,
    plan: QueryPlan,
    pages_per_query: int,
    now: datetime,
    result: DiscoveryOutcome,
) -> None:
    after, before = window_bounds(plan.window, now)
    hits: list[SearchHit] = []
    token: str | None = None
    pages = 0
    for _ in range(pages_per_query):
        quota_service.reserve(
            session, settings, endpoint="search", units=SEARCH_UNITS, run_id=run_id, now=now
        )
        params = SearchParams(
            query=plan.query,
            published_after=after,
            published_before=before,
            relevance_language=plan.language,
            region_code=plan.region,
            page_token=token,
        )
        page_hits, token = source.search(params)
        result.searches += 1
        pages += 1
        hits.extend(page_hits)
        if not token:
            break

    unique_ids = list(dict.fromkeys(h.youtube_video_id for h in hits))
    stored = enrich_and_store(
        session, source, unique_ids, run_id=run_id, now=now, settings=settings
    )

    query_row = _query_row(
        run_id, plan, now, status="OK", count=len(hits), pages=pages, warnings=[]
    )
    session.add(query_row)
    session.flush()
    for position, hit in enumerate(hits):
        video = stored.get(hit.youtube_video_id)
        if video is None:
            continue
        already = session.scalars(
            select(m.DiscoveryMatch).where(
                m.DiscoveryMatch.query_id == query_row.id, m.DiscoveryMatch.video_id == video.id
            )
        ).first()
        if already is None:
            session.add(
                m.DiscoveryMatch(
                    id=str(uuid4()),
                    run_id=run_id,
                    query_id=query_row.id,
                    video_id=video.id,
                    position=position,
                    strategy="search_list",
                    match_quality="UNREVIEWED",
                    is_spanish_market=video.language_state == "es",
                )
            )
    counts = result.per_language.setdefault(
        plan.language, {"queries": 0, "results": 0, "videos": 0}
    )
    counts["queries"] += 1
    counts["results"] += len(hits)
    counts["videos"] += len(stored)
    result.completed.append(plan.key)


def _query_row(
    run_id: str,
    plan: QueryPlan,
    now: datetime,
    *,
    status: str,
    count: int,
    pages: int,
    warnings: list[str],
) -> m.SourceQuery:
    return m.SourceQuery(
        id=str(uuid4()),
        run_id=run_id,
        provider=PROVIDER,
        language_requested=plan.language,
        region=plan.region,
        query_text=plan.query[:300],
        window_code=plan.window,
        params_json={
            "relevanceLanguage": plan.language,
            "window": plan.window,
            "regionCode": plan.region,
        },
        executed_at=now,
        result_count=count,
        pages=pages,
        status=status,
        warnings_json=warnings,
    )


def load_channel_uploads(
    session: Session,
    source: DiscoverySource,
    settings: Settings,
    channel: m.Channel,
    *,
    run_id: str | None,
    now: datetime,
    max_pages: int = 1,
) -> list[m.Video]:
    """Videos recientes de un canal vía su lista de uploads (T06). Nunca search.list por canal."""
    if not channel.uploads_playlist_id:
        return []
    ids: list[str] = []
    token: str | None = None
    for _ in range(max_pages):
        quota_service.reserve(
            session, settings, endpoint="playlistItems", units=1, run_id=run_id, now=now
        )
        page_ids, token = source.uploads(channel.uploads_playlist_id, token)
        ids.extend(page_ids)
        if not token:
            break
    stored = enrich_and_store(session, source, ids, run_id=run_id, now=now, settings=settings)
    return list(stored.values())
