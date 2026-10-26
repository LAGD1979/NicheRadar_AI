"""Señales de demanda en español (spec §3.6). Funciones puras, reglas heurísticas por calibrar.

La demanda necesita al menos **dos señales independientes** para ser «Observada». Una señal es
independiente si viene de una **familia de fuentes distinta**; varias palabras clave de la misma
fuente cuentan una sola vez.

Familias:
- `google_trends`: índice relativo (0 a 100) de búsquedas, vía HasData. Nunca es un volumen.
- `vidiq_keywords`: búsquedas mensuales estimadas por vidIQ para una palabra clave.
- `youtube_consumption`: vistas de los competidores exactos que una persona revisó.

Cada señal es `PRESENT`, `NOT_PRESENT` (se observó y no alcanza) o `UNKNOWN` (faltan datos). Que no
haya datos nunca se trata como «no hay demanda» (spec §3.6 punto 7).
"""

from dataclasses import dataclass
from statistics import fmean
from typing import Any

RULE_VERSION = "demand-v1"
TRENDS = "google_trends"
KEYWORDS = "vidiq_keywords"
CONSUMPTION = "youtube_consumption"
FAMILIES = (TRENDS, KEYWORDS, CONSUMPTION)
RECENT_WEEKS = 13
MIN_RECENT_POINTS = 8


@dataclass(frozen=True)
class SignalRules:
    trends_min_interest: float = 10
    trends_min_weeks: int = 26
    trends_max_decline_ratio: float = 0.6
    keywords_min_monthly_searches: int = 1000
    keywords_min_growth_pct: float = -50.0
    consumption_min_competitors: int = 3
    consumption_min_views: int = 50_000


@dataclass(frozen=True)
class TrendSample:
    value: int | None
    partial: bool


def rules_from_config(research: dict[str, Any]) -> SignalRules:
    return SignalRules(
        trends_min_interest=float(research.get("demand_trends_min_interest", 10)),
        trends_min_weeks=int(research.get("demand_trends_min_weeks", 26)),
        trends_max_decline_ratio=float(research.get("demand_trends_max_decline_ratio", 0.6)),
        keywords_min_monthly_searches=int(
            research.get("demand_keywords_min_monthly_searches", 1000)
        ),
        keywords_min_growth_pct=float(research.get("demand_keywords_min_growth_pct", -50)),
        consumption_min_competitors=int(research.get("demand_consumption_min_competitors", 3)),
        consumption_min_views=int(research.get("long_video_views_soft_min", 50_000)),
    )


def trends_signal(samples: list[TrendSample], rules: SignalRules | None = None) -> dict[str, Any]:
    rules = rules or SignalRules()
    complete = [s for s in samples if not s.partial]  # la semana en curso aún no es comparable
    with_data = [s for s in complete if s.value is not None]
    base: dict[str, Any] = {
        "family": TRENDS,
        "relative_index": True,
        "weeks_total": len(complete),
        "weeks_with_data": len(with_data),
        "recent_mean": None,
        "base_mean": None,
    }
    if len(with_data) < rules.trends_min_weeks:
        return {**base, "state": "UNKNOWN", "reason": "INSUFFICIENT_DATA"}
    recent_all = complete[-RECENT_WEEKS:]
    recent = [s.value for s in recent_all if s.value is not None]
    if len(recent) < MIN_RECENT_POINTS:
        return {**base, "state": "UNKNOWN", "reason": "INSUFFICIENT_RECENT_DATA"}
    earlier = [s.value for s in complete[:-RECENT_WEEKS] if s.value is not None]
    recent_mean = fmean(recent)
    base_mean = fmean(earlier) if earlier else None
    result = {
        **base,
        "recent_mean": round(recent_mean, 2),
        "base_mean": None if base_mean is None else round(base_mean, 2),
    }
    if recent_mean < rules.trends_min_interest:
        return {**result, "state": "NOT_PRESENT", "reason": "LOW_RELATIVE_INTEREST"}
    if base_mean and recent_mean < rules.trends_max_decline_ratio * base_mean:
        return {**result, "state": "NOT_PRESENT", "reason": "INTEREST_DECLINING"}
    return {**result, "state": "PRESENT", "reason": "SUSTAINED_RELATIVE_INTEREST"}


def keyword_signal(
    monthly_searches: int | None,
    growth_pct: float | None,
    rules: SignalRules | None = None,
) -> dict[str, Any]:
    rules = rules or SignalRules()
    base: dict[str, Any] = {
        "family": KEYWORDS,
        "monthly_searches": monthly_searches,
        "growth_pct": None if growth_pct is None else round(growth_pct, 1),
    }
    if monthly_searches is None:
        return {**base, "state": "UNKNOWN", "reason": "VOLUME_UNKNOWN"}
    if monthly_searches < rules.keywords_min_monthly_searches:
        return {**base, "state": "NOT_PRESENT", "reason": "BELOW_MIN_VOLUME"}
    if growth_pct is not None and growth_pct < rules.keywords_min_growth_pct:
        return {**base, "state": "NOT_PRESENT", "reason": "SEARCHES_FALLING"}
    return {**base, "state": "PRESENT", "reason": "SEARCH_VOLUME_OBSERVED"}


def consumption_signal(
    exact_views: dict[str, int | None], rules: SignalRules | None = None
) -> dict[str, Any]:
    """Consumo de los competidores exactos revisados: `{video_id: vistas}`."""
    rules = rules or SignalRules()
    known = [v for v in exact_views.values() if v is not None]
    strong = [v for v in known if v >= rules.consumption_min_views]
    base: dict[str, Any] = {
        "family": CONSUMPTION,
        "exact_competitors": len(exact_views),
        "with_views": len(known),
        "strong_competitors": len(strong),
        "min_views": rules.consumption_min_views,
    }
    if not exact_views:
        return {**base, "state": "UNKNOWN", "reason": "NO_EXACT_MATCHES"}
    if len(known) < rules.consumption_min_competitors:
        return {**base, "state": "UNKNOWN", "reason": "INSUFFICIENT_SAMPLE"}
    if len(strong) >= rules.consumption_min_competitors:
        return {**base, "state": "PRESENT", "reason": "COMPETITORS_WITH_HIGH_VIEWS"}
    return {**base, "state": "NOT_PRESENT", "reason": "FEW_COMPETITORS_WITH_HIGH_VIEWS"}


_ORDER = {"PRESENT": 2, "NOT_PRESENT": 1, "UNKNOWN": 0}


def combine(signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Un estado por familia (el mejor observado) y cuántas familias distintas están presentes."""
    by_family: dict[str, str] = {}
    for signal in signals:
        family = str(signal.get("family"))
        state = str(signal.get("state", "UNKNOWN"))
        if _ORDER.get(state, 0) >= _ORDER.get(by_family.get(family, "UNKNOWN"), 0):
            by_family[family] = state
    present = sorted(f for f, s in by_family.items() if s == "PRESENT")
    return {
        "independent_signals": len(present),
        "present_families": present,
        "family_states": {f: by_family.get(f, "UNKNOWN") for f in FAMILIES},
        "rule_version": RULE_VERSION,
    }
