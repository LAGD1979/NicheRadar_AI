"""Contexto que recibe el asistente de IA (D-67): agregado y sin datos particulares.

El asistente ve el **resumen** de una oportunidad, no sus registros. Nunca se incluyen títulos de
videos, nombres de canales, identificadores ni enlaces: solo conteos, estados, índices, medianas y
valores que la persona escribió (costos y niveles). El texto libre de las valoraciones tampoco
viaja. Así el contexto es pequeño (unos 1.500 tokens), barato y no distribuye datos de terceros
individuales.

Cada sección tiene una clave estable (`SECTIONS`); el asistente cita esas claves y la API descarta
las que no existan. Lo que está restringido por política o sin datos no se inventa: va a `missing`.
"""

import statistics
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m
from app.services import (
    demand_state,
    feasibility_service,
    opportunity_service,
    spanish_service,
)
from app.services.compliance_service import decide

CONTEXT_VERSION = "ctx-v1"
SECTIONS = (
    "opportunity",
    "evaluation",
    "international",
    "spanish_market",
    "demand",
    "competitors",
    "production",
    "scores",
    "missing",
)
SUBSCRIBER_BANDS = (
    (10_000, "menos de 10 mil"),
    (50_000, "10 mil a 50 mil"),
    (200_000, "50 mil a 200 mil"),
)
TOP_BAND = "más de 200 mil"
UNREVIEWED = "UNREVIEWED"

INTERNATIONAL_KEYS = (
    "replication_state",
    "independent_channels_observed",
    "relevant_videos_observed",
    "successful_videos_observed",
    "distinct_weeks",
    "top_channel_concentration",
    "max_videos_per_channel",
    "independence_verified",
    "sample_bias_warning",
    "reason_codes",
    "temporal_resilience",
)
SPANISH_KEYS = (
    "saturation_state",
    "spanish_demand_state",
    "entry_decision",
    "exact_matches",
    "reviewed_matches",
    "es_verified_videos",
    "query_variants",
    "query_coverage_count",
    "match_precision_reviewed",
    "reason_codes",
    "small_channel_access",
)
FEASIBILITY_KEYS = (
    "faceless_state",
    "complexity_1_to_5",
    "rights_risk",
    "human_review_required",
    "human_minutes_per_video",
    "ai_pipeline_coverage_pct",
    "usd_per_video_scenarios",
    "costs_are_estimates",
)


def _pick(source: dict[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any]:
    data = source or {}
    return {key: data[key] for key in keys if key in data}


def _band(subscribers: int | None) -> str:
    if subscribers is None:
        return "sin dato"
    for limit, label in SUBSCRIBER_BANDS:
        if subscribers < limit:
            return label
    return TOP_BAND


def _demand(
    session: Session, settings: Settings, opportunity_id: str, now: datetime
) -> dict[str, Any]:
    summary = demand_state.summary(session, settings, opportunity_id, now)
    signals: list[dict[str, Any]] = []
    for signal in summary["signals"]:
        details = signal.get("details") or {}
        row: dict[str, Any] = {
            "family": signal.get("family"),
            "state": signal.get("state"),
            "reason": signal.get("reason"),
        }
        if signal.get("keyword"):
            row["keyword"] = signal["keyword"]
            row["country"] = signal.get("geo") or "todos"
        for key in (
            "recent_mean",
            "base_mean",
            "share_of_leader",
            "monthly_searches",
            "growth_pct",
            "strong_competitors",
            "exact_competitors",
        ):
            if details.get(key) is not None:
                row[key] = details[key]
        if signal.get("expires_at"):
            row["expires_at"] = signal["expires_at"]
        signals.append(row)
    return {
        "independent_signals": summary["independent_signals"],
        "family_states": summary["family_states"],
        "signals": signals,
    }


def _competitors(
    session: Session, settings: Settings, opportunity_id: str, now: datetime
) -> dict[str, Any]:
    """Conteos y distribuciones de los videos en español; nunca el listado."""
    rows = spanish_service.competition(session, opportunity_id)
    spanish = [r for r in rows if r["is_spanish_market"]]
    by_quality: dict[str, int] = {}
    ai_suggested: dict[str, int] = {}
    for row in spanish:
        quality = str(row["match_quality"])
        by_quality[quality] = by_quality.get(quality, 0) + 1
        if quality == UNREVIEWED and row.get("ai_quality"):
            suggestion = str(row["ai_quality"])
            ai_suggested[suggestion] = ai_suggested.get(suggestion, 0) + 1
    out: dict[str, Any] = {
        "videos_total": len(rows),
        "videos_spanish": len(spanish),
        "reviewed_by_person": len(spanish) - by_quality.get(UNREVIEWED, 0),
        "by_person_review": {k: v for k, v in by_quality.items() if k != UNREVIEWED},
        "unreviewed": by_quality.get(UNREVIEWED, 0),
        "unreviewed_by_ai_suggestion": ai_suggested,
    }
    if not decide("derived_metrics", settings, session, now).allowed:
        out["exact_competitors_audience"] = "restringido por política"
        return out
    stats = session.execute(
        select(m.Video.view_count, m.Channel.subscriber_count)
        .join(m.DiscoveryMatch, m.DiscoveryMatch.video_id == m.Video.id)
        .join(m.Channel, m.Channel.id == m.Video.channel_id)
        .where(
            m.DiscoveryMatch.opportunity_id == opportunity_id,
            m.DiscoveryMatch.match_quality == "EXACT",
            m.DiscoveryMatch.is_spanish_market.is_(True),
            m.Video.availability != "EXPIRED",
        )
        .distinct()
    ).all()
    views = [int(v) for v, _ in stats if v is not None]
    bands: dict[str, int] = {}
    for _, subscribers in stats:
        label = _band(subscribers)
        bands[label] = bands.get(label, 0) + 1
    out["exact_competitors_audience"] = {
        "videos": len(stats),
        "views_median": int(statistics.median(views)) if views else None,
        "views_max": max(views) if views else None,
        "channels_by_subscriber_band": bands,
    }
    return out


def _production(
    session: Session, opportunity_id: str, feasibility: dict[str, Any]
) -> dict[str, Any]:
    out = _pick(feasibility, FEASIBILITY_KEYS)
    editorial = feasibility.get("editorial") or {}
    if editorial:
        out["editorial"] = {
            "differentiation": (editorial.get("differentiation") or {}).get("level"),
            "maintainability": (editorial.get("maintainability") or {}).get("level"),
        }
    cost = feasibility_service.latest_cost_model(session, opportunity_id)
    if cost is not None:
        out["cost_model"] = {
            "lines": len(cost.params_json.get("lines", [])),
            "missing_prices_by_scenario": cost.missing_json,
        }
    return out


def _missing(context: dict[str, Any]) -> list[str]:
    """Qué falta, dicho en lenguaje llano: el asistente puede sugerir el siguiente paso con esto."""
    gaps: list[str] = []
    spanish = context["spanish_market"]
    competitors = context["competitors"]
    if spanish.get("saturation_state") in (None, "UNKNOWN"):
        gaps.append(
            "Saturación en español desconocida: falta revisar competidores "
            f"({competitors['unreviewed']} sin revisar de {competitors['videos_spanish']})."
        )
    if context["demand"]["independent_signals"] < 2:
        gaps.append("Demanda en español con menos de dos señales independientes.")
    if not context["production"].get("usd_per_video_scenarios"):
        gaps.append("Falta el modelo de costo por video.")
    if not context["production"].get("faceless_state"):
        gaps.append("Falta la valoración de factibilidad (faceless, complejidad, derechos).")
    if not context["production"].get("editorial"):
        gaps.append("Falta la valoración editorial (diferenciación y mantenibilidad).")
    for name, score in context["scores"].items():
        if score.get("state") != "AVAILABLE":
            gaps.append(f"Índice {name} no disponible: {score.get('reason') or 'sin motivo'}.")
    return gaps


def build(session: Session, settings: Settings, opportunity_id: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    detail = opportunity_service.get_opportunity_detail(session, settings, opportunity_id)
    evaluation = detail.evaluation
    feasibility = (evaluation.feasibility if evaluation else None) or {}
    scores = {
        name: {"value": s.value, "state": s.state, "reason": s.reason}
        for name, s in (evaluation.scores if evaluation else {}).items()
    }
    context: dict[str, Any] = {
        "context_version": CONTEXT_VERSION,
        "generated_at": now.isoformat(),
        "opportunity": {
            "niche": detail.niche.name,
            "niche_definition": detail.niche.definition,
            "format": detail.format.name,
            "format_story_structure": detail.format.story_structure,
            "format_visual_grammar": detail.format.visual_grammar,
            "video_type": detail.video_type,
            "target_language": detail.target_lang,
            "status": detail.status,
        },
        "evaluation": (
            {
                "confidence": evaluation.confidence,
                "recommendation": evaluation.recommendation,
                "reason_codes": evaluation.reason_codes,
                "metric_policy_state": evaluation.metric_policy_state,
                "observed_at": evaluation.observed_at.isoformat(),
            }
            if evaluation
            else None
        ),
        "international": _pick(
            evaluation.international if evaluation else None, INTERNATIONAL_KEYS
        ),
        "spanish_market": _pick(evaluation.spanish if evaluation else None, SPANISH_KEYS),
        "demand": _demand(session, settings, opportunity_id, now),
        "competitors": _competitors(session, settings, opportunity_id, now),
        "production": _production(session, opportunity_id, feasibility),
        "scores": scores,
    }
    context["missing"] = _missing(context)
    return context
