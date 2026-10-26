"""Medición de demanda en español con fuentes externas (D-63).

- Trends vía HasData (REST): índice relativo semanal en YouTube. Los términos pendientes se piden
  **juntos** en una llamada (hasta 5, 10 créditos): así sus índices son comparables entre sí. Los
  topes diario y mensual locales cuentan llamadas. Una medición reciente con los mismos términos se
  reutiliza en vez de gastar créditos otra vez.
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
    def compare_interest(
        self, queries: list[str], *, geo: str = ..., date: str = ..., gprop: str = ...
    ) -> dict[str, list[TrendPoint]]: ...

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
    reused: int = 0
    vidiq_credits: int = 0
    observations: int = 0


def month_start(now: datetime) -> datetime:
    return vidiq_service.day_start(now).replace(day=1)


def _hasdata_calls_since(session: Session, start: datetime) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(m.ProviderUsage.units), 0)).where(
            m.ProviderUsage.provider == HASDATA,
            m.ProviderUsage.quota_bucket == HASDATA_BUCKET,
            m.ProviderUsage.started_at >= start,
        )
    )
    return int(total or 0)


def hasdata_calls_today(session: Session, now: datetime) -> int:
    return _hasdata_calls_since(session, vidiq_service.day_start(now))


def hasdata_calls_month(session: Session, now: datetime) -> int:
    return _hasdata_calls_since(session, month_start(now))


def reserve_hasdata(
    session: Session, settings: Settings, run_id: str | None, now: datetime
) -> None:
    used = hasdata_calls_today(session, now)
    if used + 1 > settings.hasdata_daily_call_limit:
        raise QuotaExhausted(
            "Tope diario local de consultas a HasData: "
            f"{used} de {settings.hasdata_daily_call_limit}."
        )
    used_month = hasdata_calls_month(session, now)
    if used_month + 1 > settings.hasdata_monthly_call_limit:
        raise QuotaExhausted(
            "Tope mensual local de consultas a HasData: "
            f"{used_month} de {settings.hasdata_monthly_call_limit}."
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
    used_month = hasdata_calls_month(session, now)
    return {
        "provider": HASDATA,
        "quota_bucket": HASDATA_BUCKET,
        "day_start_utc": vidiq_service.day_start(now).isoformat(),
        "calls_used": used,
        "calls_daily_limit": settings.hasdata_daily_call_limit,
        "calls_remaining": max(0, settings.hasdata_daily_call_limit - used),
        "month_start_utc": month_start(now).isoformat(),
        "calls_month_used": used_month,
        "calls_monthly_limit": settings.hasdata_monthly_call_limit,
        "calls_month_remaining": max(0, settings.hasdata_monthly_call_limit - used_month),
    }


def group_key(terms: list[str]) -> list[str]:
    """Identifica un conjunto de términos medidos juntos (sin orden ni mayúsculas)."""
    return sorted(t.lower() for t in terms)


def fresh_trends(
    session: Session,
    settings: Settings,
    *,
    opportunity_id: str,
    terms: list[str],
    geo: str | None,
    include_related: bool,
    now: datetime,
) -> bool:
    """¿Ya hay una medición vigente de estos mismos términos, hecha en el mismo grupo?"""
    since = now - timedelta(days=settings.hasdata_reuse_days)
    wanted = group_key(terms)
    for term in terms:
        row = session.scalars(
            select(m.DemandObservation)
            .where(
                m.DemandObservation.opportunity_id == opportunity_id,
                m.DemandObservation.provider == HASDATA,
                m.DemandObservation.availability == "AVAILABLE",
                func.lower(m.DemandObservation.keyword) == term.lower(),
                m.DemandObservation.geo.is_(None) if not geo else m.DemandObservation.geo == geo,
                m.DemandObservation.observed_at >= since,
            )
            .order_by(m.DemandObservation.observed_at.desc())
        ).first()
        if row is None:
            return False
        result = row.result_json or {}
        if result.get("comparison_group") != wanted:
            return False
        if include_related and "related" not in result:
            return False
    return True


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


def _record_error(result: DemandOutcome, exc: Exception, source: str, label: str) -> bool:
    """Anota el error de un proveedor y dice si hay que detener toda la corrida."""
    if isinstance(exc, QuotaExhausted):
        result.outcome = "PAUSED_QUOTA"
        result.errors.append({"code": "PAUSED_QUOTA", "detail": str(exc)})
        return True
    if isinstance(exc, ProviderAuthError):
        result.outcome = "FAILED"
        result.errors.append({"code": "AUTH_ERROR", "detail": f"{source}: {exc}"})
        return True
    code = exc.code if isinstance(exc, ProviderUnavailable | InvalidRequest) else "ERROR"
    if result.outcome == "COMPLETED":
        result.outcome = "PARTIAL"
    result.errors.append({"code": code, "detail": f"{source} · {label}: {exc}"})
    return False


def _observe_trends(
    session: Session,
    settings: Settings,
    result: DemandOutcome,
    *,
    opportunity_id: str,
    terms: list[str],
    geo: str | None,
    include_related: bool,
    trends: TrendsSource,
    run_id: str | None,
    completed_keys: set[str],
    force: bool,
    rules: ds.SignalRules,
    now: datetime,
) -> bool:
    """Mide los términos pendientes **juntos** (índices comparables). Devuelve si hay que parar."""
    pending = [t for t in terms if f"trends:{t.lower()}:{geo or ''}" not in completed_keys]
    if not pending:
        return False
    keys = [f"trends:{t.lower()}:{geo or ''}" for t in pending]
    if not force and fresh_trends(
        session,
        settings,
        opportunity_id=opportunity_id,
        terms=pending,
        geo=geo,
        include_related=include_related,
        now=now,
    ):
        result.reused += 1
        result.completed.extend(keys)
        completed_keys.update(keys)
        return False
    try:
        reserve_hasdata(session, settings, run_id, now)
        result.hasdata_calls += 1
        series = trends.compare_interest(
            pending, geo=geo or "", date=TRENDS_DATE, gprop=TRENDS_GPROP
        )
    except (QuotaExhausted, ProviderAuthError, ProviderUnavailable, InvalidRequest) as exc:
        return _record_error(result, exc, "trends", ", ".join(pending))
    grouped = len(pending) > 1
    signals = {
        t: ds.trends_signal([ds.TrendSample(p.value, p.partial) for p in series.get(t, [])], rules)
        for t in pending
    }
    leader = max(
        (float(sg["recent_mean"]) for sg in signals.values() if sg["recent_mean"]), default=0.0
    )
    stop = False
    for term, key in zip(pending, keys, strict=True):
        signal = signals[term]
        if grouped and signal["reason"] == "LOW_RELATIVE_INTEREST":
            # Contra un término más fuerte, un índice bajo no prueba que falte demanda.
            signal = {**signal, "state": "UNKNOWN", "reason": "LOW_IN_COMPARISON"}
        points = series.get(term, [])
        recent = signal["recent_mean"]
        details: dict[str, Any] = {
            "gprop": TRENDS_GPROP,
            "date": TRENDS_DATE,
            "series": [p.value for p in points if not p.partial],
            "comparison_group": group_key(pending),
            "terms": pending,
            "share_of_leader": (
                round(float(recent) / leader * 100, 1) if grouped and recent and leader else None
            ),
        }
        if include_related and not stop:
            try:
                reserve_hasdata(session, settings, run_id, now)
                result.hasdata_calls += 1
                related = trends.related_queries(
                    term, geo=geo or "", date=TRENDS_DATE, gprop=TRENDS_GPROP
                )
                details["related"] = [
                    {"query": r.query, "kind": r.kind, "value": r.value} for r in related[:20]
                ]
            except (QuotaExhausted, ProviderAuthError, ProviderUnavailable, InvalidRequest) as exc:
                stop = _record_error(result, exc, "trends", f"{term} (relacionadas)")
        _store(
            session,
            settings,
            opportunity_id=opportunity_id,
            family=ds.TRENDS,
            provider=HASDATA,
            keyword=term,
            geo=geo,
            signal=signal,
            details=details,
            run_id=run_id,
            now=now,
        )
        result.observations += 1
        result.completed.append(key)
        completed_keys.add(key)
    return stop


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
    force: bool = False,
) -> DemandOutcome:
    rules = demand_state.rules_for(settings)
    result = DemandOutcome(completed=sorted(completed_keys))
    terms = list(dict.fromkeys(keywords[:MAX_KEYWORDS]))
    stop = False
    if "trends" in sources and trends is not None:
        stop = _observe_trends(
            session,
            settings,
            result,
            opportunity_id=opportunity_id,
            terms=terms,
            geo=geo,
            include_related=include_related,
            trends=trends,
            run_id=run_id,
            completed_keys=completed_keys,
            force=force,
            rules=rules,
            now=now,
        )
    if "vidiq" in sources and vidiq is not None and not stop:
        for keyword in terms:
            key = f"vidiq:{keyword.lower()}:{geo or ''}"
            if key in completed_keys:
                continue
            try:
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
                    signal = ds.keyword_signal(metrics.monthly_searches, metrics.growth_pct, rules)
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
                result.observations += 1
                result.completed.append(key)
                completed_keys.add(key)
            except (QuotaExhausted, ProviderAuthError, ProviderUnavailable, InvalidRequest) as exc:
                if _record_error(result, exc, "vidiq", keyword):
                    break
    result.completed = sorted(set(result.completed))
    if result.observations:
        spanish_service.record_assessment(session, opportunity_id, run_id, now)
    return result
