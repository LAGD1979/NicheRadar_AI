"""Lectura de las señales de demanda de una oportunidad (D-63).

Reúne las observaciones vigentes de fuentes externas (Trends vía HasData, palabras clave de
vidIQ) y el consumo de los competidores exactos revisados, y las combina en señales
independientes. No llama a ningún proveedor: eso es `demand_service`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.research_config import load_research_config
from app.db import models as m
from app.domain import demand_signals as ds
from app.services.compliance_service import decide


def rules_for(settings: Settings) -> ds.SignalRules:
    research = load_research_config(settings.research_config_path)["research"]
    return ds.rules_from_config(research)


def latest_observations(
    session: Session, opportunity_id: str, now: datetime
) -> list[m.DemandObservation]:
    """La observación más reciente por proveedor, palabra clave y país; sin vencidas."""
    rows = session.scalars(
        select(m.DemandObservation)
        .where(
            m.DemandObservation.opportunity_id == opportunity_id,
            m.DemandObservation.availability == "AVAILABLE",
        )
        .order_by(m.DemandObservation.observed_at.desc())
    ).all()
    seen: set[tuple[str, str, str]] = set()
    latest: list[m.DemandObservation] = []
    for row in rows:
        if row.retention_deadline is not None and row.retention_deadline < now:
            continue
        key = (row.provider, row.keyword.lower(), row.geo or "")
        if key in seen:
            continue
        seen.add(key)
        latest.append(row)
    return latest


def _observation_signal(row: m.DemandObservation) -> dict[str, Any]:
    return {
        "family": row.family,
        "state": row.state,
        "reason": row.reason,
        "keyword": row.keyword,
        "geo": row.geo,
        "provider": row.provider,
        "observed_at": row.observed_at.isoformat(),
        "expires_at": row.retention_deadline.isoformat() if row.retention_deadline else None,
        "details": row.result_json,
    }


def consumption_signal(
    session: Session, settings: Settings, opportunity_id: str, now: datetime
) -> dict[str, Any]:
    """Consumo de los competidores exactos revisados (métrica derivada: exige la compuerta)."""
    if not decide("derived_metrics", settings, session, now).allowed:
        return {"family": ds.CONSUMPTION, "state": "UNKNOWN", "reason": "RESTRICTED"}
    rows = session.execute(
        select(m.Video.youtube_video_id, m.Video.view_count)
        .join(m.DiscoveryMatch, m.DiscoveryMatch.video_id == m.Video.id)
        .where(
            m.DiscoveryMatch.opportunity_id == opportunity_id,
            m.DiscoveryMatch.match_quality == "EXACT",
            m.DiscoveryMatch.is_spanish_market.is_(True),
            m.Video.availability != "EXPIRED",
        )
    ).all()
    return ds.consumption_signal({vid: views for vid, views in rows}, rules_for(settings))


def summary(
    session: Session, settings: Settings, opportunity_id: str, now: datetime
) -> dict[str, Any]:
    signals = [
        _observation_signal(row) for row in latest_observations(session, opportunity_id, now)
    ]
    signals.append(consumption_signal(session, settings, opportunity_id, now))
    return {**ds.combine(signals), "signals": signals}
