"""Replicación internacional de una oportunidad a partir de los videos agrupados por una persona.

- Es una métrica derivada: solo corre si la capacidad `derived_metrics` está abierta (D-48). Si no,
  la sección internacional queda como estaba y se informa la restricción.
- Cada cambio de resultado crea una versión nueva de la evaluación (append-only, D-36).
- Un video caducado (purga de 29 días) deja de contar: nunca se usan datos vencidos.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.research_config import load_research_config
from app.db import models as m
from app.domain.replication import ReplicationVideo, classify, rules_from_config
from app.services import evaluation_service
from app.services.compliance_service import decide

STRENGTH = {"HIGH": "STRONG", "MEDIUM": "MEDIUM", "LOW": "WEAK"}
SOURCE = "CALCULATED"


def ensure_evidence(session: Session, opportunity: m.Opportunity, now: datetime) -> int:
    """Una fila de evidencia por video agrupado, para que la ficha y la IA la vean. Idempotente."""
    rows = session.execute(
        select(m.VideoAnnotation, m.Video)
        .join(m.Video, m.Video.id == m.VideoAnnotation.video_id)
        .where(m.VideoAnnotation.opportunity_id == opportunity.id)
        .order_by(m.VideoAnnotation.created_at)
    ).all()
    existing = set(
        session.scalars(
            select(m.OpportunityEvidence.entity_id).where(
                m.OpportunityEvidence.opportunity_id == opportunity.id,
                m.OpportunityEvidence.entity_type == "VIDEO",
            )
        )
    )
    created = 0
    for annotation, video in rows:
        if video.youtube_video_id in existing:
            continue
        existing.add(video.youtube_video_id)
        session.add(
            m.OpportunityEvidence(
                id=str(uuid4()),
                opportunity_id=opportunity.id,
                entity_type="VIDEO",
                entity_id=video.youtube_video_id,
                market="SOURCE_MARKET",
                role="INTL_EXAMPLE",
                evidence_text=annotation.rationale,
                source=video.provider,
                observed_at=now,
                support_strength=STRENGTH.get(annotation.same_format_confidence, "WEAK"),
                availability="AVAILABLE",
                source_data_type=video.source_data_type,
            )
        )
        created += 1
    session.flush()
    return created


def _collect(session: Session, opportunity_id: str) -> list[ReplicationVideo]:
    rows = session.execute(
        select(m.VideoAnnotation, m.Video, m.Channel)
        .join(m.Video, m.Video.id == m.VideoAnnotation.video_id)
        .join(m.Channel, m.Channel.id == m.Video.channel_id)
        .where(
            m.VideoAnnotation.opportunity_id == opportunity_id,
            m.Video.availability != "EXPIRED",
        )
    ).all()
    return [
        ReplicationVideo(
            video_id=video.youtube_video_id,
            channel_id=channel.youtube_channel_id,
            creator_group=channel.youtube_channel_id,  # sin revisión de canales espejo (T12)
            published_at=video.published_at,
            view_count=video.view_count,
            subscriber_count=channel.subscriber_count,
            confidence=annotation.same_format_confidence,
        )
        for annotation, video, channel in rows
    ]


def refresh(
    session: Session,
    settings: Settings,
    opportunity_id: str,
    now: datetime,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Recalcula la replicación. Devuelve el resultado o `{"state": "RESTRICTED", ...}`."""
    opportunity = session.get(m.Opportunity, opportunity_id)
    if opportunity is None:
        raise LookupError(f"Oportunidad inexistente: {opportunity_id}")
    decision = decide("derived_metrics", settings, session, now)
    if not decision.allowed:
        return {"state": "RESTRICTED", "reason": decision.reason}

    ensure_evidence(session, opportunity, now)
    research = load_research_config(settings.research_config_path)["research"]
    result = classify(_collect(session, opportunity_id), rules_from_config(research))

    previous = evaluation_service.latest_evaluation(session, opportunity_id)
    # Se conservan las otras claves internacionales (p. ej. la resiliencia temporal).
    merged = {**(previous.international_json if previous else {}), **result}
    if previous is None or previous.international_json != merged:
        evaluation_service.append_evaluation(
            session,
            opportunity_id,
            now=now,
            source=SOURCE,
            run_id=run_id,
            international=merged,
        )
    return {"state": result["replication_state"], "result": result}
