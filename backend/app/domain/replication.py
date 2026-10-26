"""Replicación internacional de un formato (spec §3.4, §10.3). Reglas heurísticas por calibrar.

Función pura: recibe los videos que una persona confirmó como del mismo nicho y formato y devuelve
el estado con sus métricas y motivos. No lee base de datos ni red.

Límites que el resultado declara siempre:
- `independence_verified=False`: un canal distinto no prueba un creador distinto (canales espejo
  pendientes, T12). El agrupador `creator_group` permite corregirlo cuando exista esa revisión.
- `sample_bias_warning`: los videos salen de búsquedas y de una selección humana; no son una
  muestra del universo de YouTube.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

RULE_VERSION = "repl-v1"
STATES = ("REPLICATED", "PROMISING", "SINGLE_OUTLIER", "UNKNOWN")


@dataclass(frozen=True)
class ReplicationRules:
    min_channels_replicated: int = 3
    min_weeks_replicated: int = 3
    min_videos_per_channel: int = 2
    min_videos_distributed: int = 6
    max_top_concentration: float = 0.6
    min_channels_promising: int = 2
    min_videos_promising: int = 4
    min_weeks_promising: int = 2
    # Un video «exitoso» tiene vistas suficientes y es de un canal pequeño (research.yaml).
    success_min_views: int = 50_000
    success_max_subscribers: int = 50_000


@dataclass(frozen=True)
class ReplicationVideo:
    video_id: str
    channel_id: str
    creator_group: str
    published_at: datetime
    view_count: int | None
    subscriber_count: int | None
    confidence: str  # HIGH | MEDIUM | LOW (la que fijó la persona al agrupar)


def rules_from_config(research: dict[str, Any]) -> ReplicationRules:
    return ReplicationRules(
        min_channels_replicated=int(research.get("minimum_independent_creators_for_replicated", 3)),
        min_weeks_replicated=int(research.get("minimum_distinct_weeks_for_replicated", 3)),
        success_min_views=int(research.get("long_video_views_soft_min", 50_000)),
        success_max_subscribers=int(research.get("candidate_channel_subscribers_soft_max", 50_000)),
    )


def _iso_week(moment: datetime) -> tuple[int, int]:
    year, week, _day = moment.isocalendar()
    return year, week


def _is_success(video: ReplicationVideo, rules: ReplicationRules) -> bool:
    return (
        video.view_count is not None
        and video.subscriber_count is not None
        and video.view_count >= rules.success_min_views
        and video.subscriber_count <= rules.success_max_subscribers
    )


def classify(
    videos: list[ReplicationVideo], rules: ReplicationRules | None = None
) -> dict[str, Any]:
    rules = rules or ReplicationRules()
    unique: dict[str, ReplicationVideo] = {}
    for video in videos:
        unique.setdefault(video.video_id, video)
    excluded_low = sum(1 for v in unique.values() if v.confidence not in ("HIGH", "MEDIUM"))
    relevant = [v for v in unique.values() if v.confidence in ("HIGH", "MEDIUM")]

    groups = Counter(v.creator_group for v in relevant)
    weeks = {_iso_week(v.published_at) for v in relevant}
    complete = [v for v in relevant if v.view_count is not None and v.subscriber_count is not None]
    successes = [v for v in relevant if _is_success(v, rules)]
    success_groups = Counter(v.creator_group for v in successes)
    concentration = (
        max(success_groups.values()) / len(successes) if successes else None
    )  # denominador > 0; sin éxitos no hay concentración que medir

    reasons: list[str] = []
    state = "UNKNOWN"
    if not relevant:
        reasons.append("NO_RELEVANT_VIDEOS")
    elif not complete:
        reasons.append("SUCCESS_DATA_MISSING")
    elif len(groups) <= 1:
        state = "SINGLE_OUTLIER"
        reasons.append("ONE_CREATOR_GROUP")
    elif len(successes) <= 1:
        state = "SINGLE_OUTLIER"
        reasons.append("SUCCESS_IN_ONE_VIDEO")
    else:
        spread = all(count >= rules.min_videos_per_channel for count in groups.values()) or (
            len(relevant) >= rules.min_videos_distributed
        )
        replicated = (
            len(groups) >= rules.min_channels_replicated
            and spread
            and len(weeks) >= rules.min_weeks_replicated
            and concentration is not None
            and concentration < rules.max_top_concentration
        )
        promising = (
            len(groups) >= rules.min_channels_promising
            and len(relevant) >= rules.min_videos_promising
            and len(weeks) >= rules.min_weeks_promising
        )
        if replicated:
            state = "REPLICATED"
        elif promising:
            state = "PROMISING"
            reasons.append("BELOW_REPLICATED_THRESHOLDS")
        else:
            reasons.append("REPLICATION_INSUFFICIENT_SAMPLE")

    if len(complete) < len(relevant):
        reasons.append("SOME_VIDEOS_MISSING_VIEWS_OR_SUBSCRIBERS")
    if excluded_low:
        reasons.append("LOW_CONFIDENCE_VIDEOS_EXCLUDED")

    return {
        "replication_state": state,
        "independent_channels_observed": len(groups),
        "relevant_videos_observed": len(relevant),
        "successful_videos_observed": len(successes),
        "distinct_weeks": len(weeks),
        "top_channel_concentration": None if concentration is None else round(concentration, 3),
        "max_videos_per_channel": max(groups.values()) if groups else 0,
        "excluded_low_confidence": excluded_low,
        "reason_codes": reasons,
        "rule_version": RULE_VERSION,
        "independence_verified": False,
        "sample_bias_warning": "coverage_nonrepresentative",
    }
