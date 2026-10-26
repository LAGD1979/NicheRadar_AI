"""Persistencia de la velocidad de los videos de una oportunidad (resiliencia temporal, D-63).

Para cada video agrupado con confianza alta o media y vigente, se pide a vidIQ su serie diaria de
vistas (5 créditos) y se mide si mantiene su ritmo (`domain/persistence.py`). El resultado por
video queda en `videos.provider_metrics["vidiq_history"]` (se purga con el video) y el agregado
(mediana) en la evaluación internacional.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.research_config import load_research_config
from app.db import models as m
from app.domain import persistence as pers
from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderUnavailable,
    QuotaExhausted,
)
from app.providers.vidiq_mcp import HistoryPoint
from app.services import evaluation_service, vidiq_service

FRESH_FOR = timedelta(hours=24)
SOURCE = "CALCULATED"


class HistorySource(Protocol):
    def video_history(self, video_id: str) -> list[HistoryPoint]: ...


@dataclass
class HistoryOutcome:
    errors: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "COMPLETED"
    calls: int = 0
    credits: int = 0
    videos_measured: int = 0
    videos_skipped_fresh: int = 0
    aggregate: dict[str, Any] = field(default_factory=dict)


def _rules(settings: Settings) -> pers.PersistenceRules:
    return pers.rules_from_config(load_research_config(settings.research_config_path)["research"])


def relevant_videos(session: Session, opportunity_id: str) -> list[m.Video]:
    rows = session.execute(
        select(m.Video)
        .join(m.VideoAnnotation, m.VideoAnnotation.video_id == m.Video.id)
        .where(
            m.VideoAnnotation.opportunity_id == opportunity_id,
            m.VideoAnnotation.same_format_confidence.in_(("HIGH", "MEDIUM")),
            m.Video.availability != "EXPIRED",
        )
        .order_by(m.Video.published_at)
    ).all()
    unique: dict[str, m.Video] = {}
    for (video,) in rows:
        unique.setdefault(video.id, video)
    return list(unique.values())


def _is_fresh(video: m.Video, now: datetime) -> bool:
    history = (video.provider_metrics or {}).get("vidiq_history") or {}
    observed = history.get("observed_at")
    if not isinstance(observed, str) or history.get("rule_version") != pers.RULE_VERSION:
        return False  # medida con otra versión de la regla: se vuelve a calcular
    try:
        return now - datetime.fromisoformat(observed) < FRESH_FOR
    except ValueError:
        return False


def aggregate_for(session: Session, settings: Settings, opportunity_id: str) -> dict[str, Any]:
    results = [
        history
        for video in relevant_videos(session, opportunity_id)
        if (history := (video.provider_metrics or {}).get("vidiq_history")) is not None
    ]
    return pers.aggregate(results, _rules(settings))


def measure(
    session: Session,
    settings: Settings,
    source: HistorySource,
    *,
    opportunity_id: str,
    max_calls: int,
    run_id: str | None,
    now: datetime,
) -> HistoryOutcome:
    rules = _rules(settings)
    result = HistoryOutcome()
    for video in relevant_videos(session, opportunity_id):
        if _is_fresh(video, now):
            result.videos_skipped_fresh += 1
            continue
        if result.calls >= max_calls:
            result.outcome = "PARTIAL"
            result.errors.append(
                {"code": "BUDGET_CALLS", "detail": "Presupuesto de consultas agotado."}
            )
            break
        try:
            vidiq_service.reserve(
                session, settings, credits=settings.vidiq_credits_per_call, run_id=run_id, now=now
            )
            result.calls += 1
            result.credits += settings.vidiq_credits_per_call
            history = source.video_history(video.youtube_video_id)
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
            result.errors.append({"code": exc.code, "detail": f"{video.youtube_video_id}: {exc}"})
            continue
        measured = pers.video_persistence(
            [pers.Sample(at=p.timestamp, views=p.views) for p in history],
            video.published_at,
            rules,
        )
        video.provider_metrics = {
            **(video.provider_metrics or {}),
            "vidiq_history": {**measured, "observed_at": now.isoformat(), "run_id": run_id},
        }
        result.videos_measured += 1
    session.flush()

    result.aggregate = aggregate_for(session, settings, opportunity_id)
    previous = evaluation_service.latest_evaluation(session, opportunity_id)
    merged = {
        **(previous.international_json if previous else {}),
        "temporal_resilience": result.aggregate,
    }
    if previous is None or previous.international_json != merged:
        evaluation_service.append_evaluation(
            session, opportunity_id, now=now, source=SOURCE, run_id=run_id, international=merged
        )
    return result
