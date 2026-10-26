"""Persistencia de la velocidad de un video (resiliencia temporal, spec §3.4 y §10.3).

Compara la velocidad de vistas de la **segunda semana** con la de la **primera**, ambas contadas
desde la publicación: así todos los videos se miden en igualdad de condiciones, sin importar su
edad. La especificación pide la «pérdida o ganancia de velocidad en 7 a 14 días».

    primera semana = vistas ganadas entre el día 1 y el día 8 desde la publicación, por día
    segunda semana = vistas ganadas entre el día 8 y el día 15, por día
    persistencia   = segunda / primera, con tope en 1 (acelerar no suma más que mantener)

Reglas de honestidad:
- Si el historial no empieza cerca de la publicación o no llega al día 15, no se puntúa
  (`INSUFFICIENT_HISTORY`): nunca es cero.
- Una caída del acumulado de vistas (corrección de datos) cuenta como 0 ganancia y se informa.
- Es una heurística por calibrar, no una afirmación estadística. La «cola» de la semana 4 se
  informa aparte, sin puntuar.
"""

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

RULE_VERSION = "persist-v2"
SECONDS_PER_DAY = 86_400
MAX_START_GAP_DAYS = 2.0  # el historial debe empezar cerca de la publicación


@dataclass(frozen=True)
class Sample:
    at: datetime
    views: int | None


@dataclass(frozen=True)
class PersistenceRules:
    min_history_days: int = 15
    min_points: int = 10
    min_videos: int = 3


def rules_from_config(research: dict[str, Any]) -> PersistenceRules:
    return PersistenceRules(
        min_history_days=int(research.get("persistence_min_history_days", 15)),
        min_points=int(research.get("persistence_min_points", 10)),
        min_videos=int(research.get("persistence_min_videos", 3)),
    )


def _interpolate(points: list[tuple[float, int]], at: float) -> float:
    """Acumulado de vistas en el instante `at` (segundos), por interpolación lineal."""
    if at <= points[0][0]:
        return float(points[0][1])
    for (t0, v0), (t1, v1) in zip(points, points[1:], strict=False):
        if at <= t1:
            span = t1 - t0
            return v0 + (v1 - v0) * ((at - t0) / span) if span > 0 else float(v1)
    return float(points[-1][1])


def video_persistence(
    samples: list[Sample], published_at: datetime, rules: PersistenceRules | None = None
) -> dict[str, Any]:
    rules = rules or PersistenceRules()
    points: list[tuple[float, int]] = []
    for sample in sorted((s for s in samples if s.views is not None), key=lambda s: s.at):
        stamp = sample.at.timestamp()
        if points and stamp <= points[-1][0]:
            continue  # marcas de tiempo repetidas o desordenadas: se ignoran
        points.append((stamp, int(sample.views or 0)))
    t0 = published_at.timestamp()
    base: dict[str, Any] = {"points": len(points), "rule_version": RULE_VERSION, "ratio": None}
    if len(points) < rules.min_points:
        return {**base, "state": "INSUFFICIENT_HISTORY", "reason": "FEW_POINTS"}
    start_gap = (points[0][0] - t0) / SECONDS_PER_DAY
    covered_days = (points[-1][0] - t0) / SECONDS_PER_DAY
    base["days_observed"] = round(covered_days, 1)
    if start_gap > MAX_START_GAP_DAYS:
        return {**base, "state": "INSUFFICIENT_HISTORY", "reason": "HISTORY_STARTS_LATE"}
    if covered_days < max(15, rules.min_history_days):
        return {**base, "state": "INSUFFICIENT_HISTORY", "reason": "SHORT_HISTORY"}

    def views_at(day: int) -> float:
        return _interpolate(points, t0 + day * SECONDS_PER_DAY)

    first = views_at(8) - views_at(1)
    second = views_at(15) - views_at(8)
    revisions = sum(
        1
        for a, b in zip(points, points[1:], strict=False)
        if b[1] < a[1] and b[0] - t0 <= 15 * SECONDS_PER_DAY
    )
    first_rate = max(0.0, first) / 7
    second_rate = max(0.0, second) / 7
    if first_rate <= 0:
        return {**base, "state": "NO_VIEW_GAINS", "data_revisions": revisions}
    result: dict[str, Any] = {
        **base,
        "state": "OBSERVED",
        "ratio": round(min(1.0, second_rate / first_rate), 3),
        "week1_views_per_day": round(first_rate, 1),
        "week2_views_per_day": round(second_rate, 1),
        "data_revisions": revisions,
    }
    if covered_days >= 29:
        tail = max(0.0, views_at(29) - views_at(22)) / 7
        result["week4_views_per_day"] = round(tail, 1)
    return result


def aggregate(
    results: list[dict[str, Any]], rules: PersistenceRules | None = None
) -> dict[str, Any]:
    """Mediana de la persistencia de los videos con historial suficiente."""
    rules = rules or PersistenceRules()
    ratios = [r["ratio"] for r in results if isinstance(r.get("ratio"), float)]
    insufficient = len(results) - len(ratios)
    out: dict[str, Any] = {
        "videos_evaluated": len(ratios),
        "videos_without_enough_history": insufficient,
        "min_videos": rules.min_videos,
        "rule_version": RULE_VERSION,
        "definition": "views_per_day_week2_over_week1",
        "ratio": None,
    }
    if not results:
        return {**out, "state": "NO_VIDEOS"}
    if len(ratios) < rules.min_videos:
        return {**out, "state": "INSUFFICIENT_VIDEOS"}
    return {**out, "state": "OBSERVED", "ratio": round(float(median(ratios)), 3)}
