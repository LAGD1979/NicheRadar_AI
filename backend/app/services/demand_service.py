"""Medición de demanda en español con fuentes externas (D-63).

- Trends vía HasData (REST): índice relativo semanal en YouTube. Cada consulta cuesta 10 créditos
  de HasData; el tope diario local cuenta consultas.
- Palabras clave de vidIQ (MCP): búsquedas mensuales estimadas. Cada consulta cuesta 5 créditos y
  comparte el tope diario de créditos de vidIQ.
- Cada medida se guarda como observación con procedencia y caducidad de 29 días, y al terminar se
  recalcula la evaluación en español (que cuenta las señales independientes).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m
from app.domain import demand_signals as ds
from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderUnavailable,
    QuotaExhausted,
)
from app.providers.hasdata import RelatedQuery, TrendPoint
from app.providers.vidiq_mcp import KeywordMetrics
from app.services import demand_state, spanish_service, vidiq_service

HASDATA = "hasdata"
HASDATA_BUCKET = "hasdata_calls"
TRENDS_DATE = "today 12-m"
TRENDS_GPROP = "youtube"
MAX_KEYWORDS = 5
SOURCES = ("trends", "vidiq")


class TrendsSource(Protocol):
    def interest_over_time(
        self, query: str, *, geo: str = ..., date: str = ..., gprop: str = ...
    ) -> list[TrendPoint]: ...

    def related_queries(
        self, query: str, *, geo: str = ..., date: str = ..., gprop: str = ...
    ) -> list[RelatedQuery]: ...


class KeywordSource(Protocol):
    def keyword_research(
        self, keyword: str, *, country: str | None = ...
    ) -> KeywordMetrics | None: ...


@dataclass
class DemandOutcome:
    completed: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "COMPLETED"
    hasdata_calls: int = 0
    vidiq_credits: int = 0
    observations: int = 0


def hasdata_calls_today(session: Session, now: datetime) -> int:
    start = vidiq_service.day_start(now)
    total = session.scalar(
        select(func.coalesce(func.sum(m.ProviderUsage.units), 0)).where(
            m.ProviderUsage.provider == HASDATA,
            m.ProviderUsage.quota_bucket == HASDATA_BUCKET,
            m.ProviderUsage.started_at >= start,
        )
    )
    return int(total or 0)


def reserve_hasdata(
    session: Session, settings: Settings, run_id: str | None, now: datetime
) -> None:
    used = hasdata_calls_today(session, now)
    if used + 1 > settings.hasdata_daily_call_limit:
        raise QuotaExhausted(
            "Tope diario local de consultas a HasData: "
            f"{used} de {settings.hasdata_daily_call_limit}."
        )
    session.add(
        m.ProviderUsage(
            id=str(uuid4()),
            run_id=run_id,
            provider=HASDATA,
            endpoint="google_trends",
            quota_bucket=HASDATA_BUCKET,
            units=1,
            started_at=now,
            status="RESERVED",
        )
    )
    session.flush()


def hasdata_snapshot(session: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    used = hasdata_calls_today(session, now)
    return {
        "provider": HASDATA,
        "quota_bucket": HASDATA_BUCKET,
        "day_start_utc": vidiq_service.day_start(now).isoformat(),
        "calls_used": used,
        "calls_daily_limit": settings.hasdata_daily_call_limit,
        "calls_remaining": max(0, settings.hasdata_daily_call_limit - used),
    }


def _store(
    session: Session,
    settings: Settings,
    *,
    opportunity_id: str,
    family: str,
    provider: str,
    keyword: str,
    geo: str | None,
    signal: dict[str, Any],
    details: dict[str, Any],
    run_id: str | None,
    now: datetime,
) -> None:
    session.add(
        m.DemandObservation(
            id=str(uuid4()),
            opportunity_id=opportunity_id,
            family=family,
            provider=provider,
            keyword=keyword,
            geo=geo,
            state=str(signal["state"]),
            reason=str(signal["reason"]),
            result_json={**signal, **details},
            observed_at=now,
            run_id=run_id,
            source_data_type="PROVIDER",
            availability="AVAILABLE",
            retention_deadline=now + timedelta(days=settings.unauthorized_cache_days),
        )
    )
    session.flush()


def _country(geo: str | None) -> str | None:
    return geo.split("-")[0] if geo else None


def observe(
    session: Session,
    settings: Settings,
    *,
    opportunity_id: str,
    keywords: list[str],
    geo: str | None,
    sources: list[str],
    include_related: bool,
    trends: TrendsSource | None,
    vidiq: KeywordSource | None,
    run_id: str | None,
    completed_keys: set[str],
    now: datetime,
) -> DemandOutcome:
    rules = demand_state.rules_for(settings)
    result = DemandOutcome(completed=sorted(completed_keys))
    stop = False
    for keyword in keywords[:MAX_KEYWORDS]:
        for source in sources:
            key = f"{source}:{keyword.lower()}:{geo or ''}"
            if key in completed_keys:
                continue
            try:
                if source == "trends" and trends is not None:
                    reserve_hasdata(session, settings, run_id, now)
                    result.hasdata_calls += 1
                    points = trends.interest_over_time(
                        keyword, geo=geo or "", date=TRENDS_DATE, gprop=TRENDS_GPROP
                    )
                    signal = ds.trends_signal(
                        [ds.TrendSample(p.value, p.partial) for p in points], rules
                    )
                    details: dict[str, Any] = {
                        "gprop": TRENDS_GPROP,
                        "date": TRENDS_DATE,
                        "series": [p.value for p in points if not p.partial],
                    }
                    if include_related:
                        reserve_hasdata(session, settings, run_id, now)
                        result.hasdata_calls += 1
                        related = trends.related_queries(
                            keyword, geo=geo or "", date=TRENDS_DATE, gprop=TRENDS_GPROP
                        )
                        details["related"] = [
                            {"query": r.query, "kind": r.kind, "value": r.value}
                            for r in related[:20]
                        ]
                    _store(
                        session,
                        settings,
                        opportunity_id=opportunity_id,
                        family=ds.TRENDS,
                        provider=HASDATA,
                        keyword=keyword,
                        geo=geo,
                        signal=signal,
                        details=details,
                        run_id=run_id,
                        now=now,
                    )
                elif source == "vidiq" and vidiq is not None:
                    vidiq_service.reserve(
                        session,
                        settings,
                        credits=settings.vidiq_credits_per_call,
                        run_id=run_id,
                        now=now,
                    )
                    result.vidiq_credits += settings.vidiq_credits_per_call
                    metrics = vidiq.keyword_research(keyword, country=_country(geo))
                    if metrics is None:
                        signal = {
                            "family": ds.KEYWORDS,
                            "state": "UNKNOWN",
                            "reason": "KEYWORD_NOT_RETURNED",
                        }
                        details = {}
                    else:
                        signal = ds.keyword_signal(
                            metrics.monthly_searches, metrics.growth_pct, rules
                        )
                        details = {
                            "volume_score": metrics.volume_score,
                            "competition": metrics.competition,
                            "country_volume": metrics.country_volume,
                            "metrics_as_of": metrics.metrics_as_of,
                        }
                    _store(
                        session,
                        settings,
                        opportunity_id=opportunity_id,
                        family=ds.KEYWORDS,
                        provider=vidiq_service.PROVIDER,
                        keyword=keyword,
                        geo=geo,
                        signal=signal,
                        details=details,
                        run_id=run_id,
                        now=now,
                    )
                else:
                    continue
                result.observations += 1
                result.completed.append(key)
                completed_keys.add(key)
            except QuotaExhausted as exc:
                result.outcome = "PAUSED_QUOTA"
                result.errors.append({"code": "PAUSED_QUOTA", "detail": str(exc)})
                stop = True
            except ProviderAuthError as exc:
                result.outcome = "FAILED"
                result.errors.append({"code": "AUTH_ERROR", "detail": f"{source}: {exc}"})
                stop = True
            except (ProviderUnavailable, InvalidRequest) as exc:
                if result.outcome == "COMPLETED":
                    result.outcome = "PARTIAL"
                result.errors.append({"code": exc.code, "detail": f"{source} · {keyword}: {exc}"})
            if stop:
                break
        if stop:
            break
    result.completed = sorted(set(result.completed))
    if result.observations:
        spanish_service.record_assessment(session, opportunity_id, run_id, now)
    return result
