"""Cálculo de índices orientativos (M4). Solo corre si la compuerta de políticas lo permite.

Cada cálculo se guarda como una evaluación nueva, con la versión de fórmula y las dimensiones
que faltaron. Un índice ausente se muestra como NULL con su motivo, nunca como 0.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.db import models as m
from app.domain import scoring
from app.services import evaluation_service
from app.services.compliance_service import decide


def require_allowed(session: Session, settings: Settings, now: datetime) -> None:
    decision = decide("advanced_scores", settings, session, now)
    if not decision.allowed:
        raise ProblemError(403, "POLICY_RESTRICTED", "Puntuación no habilitada", decision.reason)


def cohort_cost_bounds(session: Session) -> tuple[float | None, float | None]:
    """Mínimo y máximo del costo base dentro de la cohorte (todas las oportunidades evaluadas)."""
    values: list[float] = []
    for evaluation in latest_evaluations(session):
        scenarios = evaluation.feasibility_json.get("usd_per_video_scenarios") or {}
        base = scenarios.get("base")
        if isinstance(base, int | float):
            values.append(float(base))
    if not values:
        return None, None
    return min(values), max(values)


def latest_evaluations(session: Session) -> list[m.Evaluation]:
    rows = session.scalars(
        select(m.Evaluation).order_by(
            m.Evaluation.opportunity_id, m.Evaluation.evaluation_version.desc()
        )
    ).all()
    seen: set[str] = set()
    out: list[m.Evaluation] = []
    for row in rows:
        if row.opportunity_id not in seen:
            seen.add(row.opportunity_id)
            out.append(row)
    return out


def compute_for_evaluation(
    evaluation: m.Evaluation, cost_bounds: tuple[float | None, float | None]
) -> dict[str, Any]:
    intl = evaluation.international_json
    spanish = evaluation.spanish_json
    feas = evaluation.feasibility_json
    channels = intl.get("independent_channels_observed")
    channels_value = channels if isinstance(channels, int) else None
    scenarios = feas.get("usd_per_video_scenarios") or {}
    base = scenarios.get("base")

    international = {
        "traccion": scoring.replication_ratio(_s(intl.get("replication_state"))),
        "replicabilidad": scoring.channels_ratio(channels_value),
        "resiliencia_temporal": None,  # sin serie temporal en M4: no hay dato, no hay puntuación
        "diversidad_independiente": scoring.channels_ratio(channels_value),
    }
    spanish_ratios = {
        "oferta_abordable": scoring.saturation_ratio(_s(spanish.get("saturation_state"))),
        "demanda_observable": scoring.demand_ratio(_s(spanish.get("spanish_demand_state"))),
        "exito_accesible": scoring.small_access_ratio(
            (spanish.get("small_channel_access") or {}).get("ratio")
        ),
        "diferenciacion": scoring.differentiation_ratio(
            _s(((feas.get("editorial") or {}).get("differentiation") or {}).get("level"))
        ),
    }
    operational = {
        "automatizacion": scoring.complexity_ratio(_i(feas.get("complexity_1_to_5"))),
        "costos": scoring.cost_ratio(
            float(base) if isinstance(base, int | float) else None, *cost_bounds
        ),
        "derechos_originalidad": scoring.rights_ratio(_s(feas.get("rights_risk"))),
        "mantenibilidad": scoring.maintenance_ratio(
            _s(((feas.get("editorial") or {}).get("maintainability") or {}).get("level"))
        ),
    }

    parts = {
        "international": scoring.subindex(scoring.INTERNATIONAL_WEIGHTS, international),
        "spanish": scoring.subindex(scoring.SPANISH_WEIGHTS, spanish_ratios),
        "operational": scoring.subindex(scoring.OPERATIONAL_WEIGHTS, operational),
    }
    total = scoring.integrated(
        {
            "international": _value(parts["international"]),
            "spanish": _value(parts["spanish"]),
            "operational": _value(parts["operational"]),
        }
    )
    return {
        "formula_version": scoring.FORMULA_VERSION,
        "international": _pack(parts["international"]),
        "spanish": _pack(parts["spanish"]),
        "feasibility": _pack(parts["operational"]),
        "integrated": {"value": total.value, "missing": total.missing or _missing_parts(parts)},
        "dimensions": {
            "international": international,
            "spanish": spanish_ratios,
            "operational": operational,
        },
        "cost_bounds_usd": {"min": cost_bounds[0], "max": cost_bounds[1]},
    }


def compute_and_store(
    session: Session, settings: Settings, opportunity_id: str, now: datetime
) -> m.Evaluation:
    require_allowed(session, settings, now)
    current = evaluation_service.latest_evaluation(session, opportunity_id)
    if current is None:
        raise ProblemError(409, "NO_EVALUATION", "Esta oportunidad aún no tiene evaluación")
    scores = compute_for_evaluation(current, cohort_cost_bounds(session))
    return evaluation_service.append_evaluation(
        session, opportunity_id, now=now, source="CALCULATED", scores=scores
    )


def ranking(
    session: Session, settings: Settings, opportunity_ids: list[str], now: datetime
) -> list[tuple[str, float | None]]:
    require_allowed(session, settings, now)
    items: list[tuple[str, float | None]] = []
    for opportunity_id in opportunity_ids:
        ev = evaluation_service.latest_evaluation(session, opportunity_id)
        value = None
        if ev is not None:
            integrated = ev.scores_json.get("integrated") or {}
            raw = integrated.get("value")
            value = float(raw) if isinstance(raw, int | float) else None
        items.append((opportunity_id, value))
    return scoring.rank(items)


def _s(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _i(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _value(part: scoring.Subindex) -> float | None:
    return part.value


def _pack(part: scoring.Subindex) -> dict[str, Any]:
    return {"value": part.value, "missing": part.missing}


def _missing_parts(parts: dict[str, scoring.Subindex]) -> list[str]:
    return [name for name, part in parts.items() if part.value is None]
