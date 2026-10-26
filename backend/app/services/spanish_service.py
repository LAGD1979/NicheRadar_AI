"""Mercado español (M2): anotaciones, planes de búsqueda, validación y revisión de competidores.

Reglas que este módulo hace cumplir:
- Solo se guarda un plan que pasó el esquema y cuyas fuentes existen (T13).
- Un plan aprobado no se edita: para cambiarlo se crea otro (versionado).
- La evaluación es append-only: cada cambio crea una versión nueva.
- Un competidor cuenta como EXACT solo si una persona lo confirmó.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.research_config import load_research_config
from app.db import models as m
from app.domain import small_channel_access as small_channel_access_domain
from app.domain import spanish_market
from app.domain.search_plan import SpanishSearchPlan, query_texts
from app.prompts import spanish_plan_v1 as prompt_v1
from app.providers.ai import AIClient
from app.services import demand_state, evaluation_service
from app.services.compliance_service import decide

MATCH_QUALITIES = ("UNREVIEWED", "EXACT", "ADJACENT", "GENERIC", "FALSE_POSITIVE")
ENTRY_TO_STATUS = {
    "CROWDED": "ES_COMPETITIVE",
    "DEMAND_UNPROVEN": "ES_DEMAND_UNPROVEN",
    "POTENTIAL_GAP": "ES_UNDERSERVED",
    "INSUFFICIENT_EVIDENCE": "ES_VALIDATION_IN_PROGRESS",
}


# --- oportunidades y anotaciones --------------------------------------------------------------


def ensure_opportunity(
    session: Session, *, niche_id: str, format_id: str, target_lang: str, video_type: str
) -> tuple[m.Opportunity, bool]:
    """Nicho, formato, idioma y tipo forman una sola oportunidad (T09)."""
    existing = session.scalars(
        select(m.Opportunity).where(
            m.Opportunity.niche_id == niche_id,
            m.Opportunity.format_id == format_id,
            m.Opportunity.target_lang == target_lang,
            m.Opportunity.video_type == video_type,
        )
    ).first()
    if existing is not None:
        return existing, False
    if session.get(m.Niche, niche_id) is None:
        raise ProblemError(404, "NICHE_NOT_FOUND", "Nicho no encontrado")
    if session.get(m.Format, format_id) is None:
        raise ProblemError(404, "FORMAT_NOT_FOUND", "Formato no encontrado")
    opp = m.Opportunity(
        id=str(uuid4()),
        niche_id=niche_id,
        format_id=format_id,
        target_lang=target_lang,
        video_type=video_type,
        source_languages_json=[],
        status="SCREENED",
        owner_notes=None,
    )
    session.add(opp)
    session.flush()
    return opp, True


def annotate_video(
    session: Session,
    *,
    video_id: str,
    niche_id: str,
    format_id: str,
    confidence: str,
    rationale: str,
    reviewer: str,
) -> tuple[m.VideoAnnotation, m.Opportunity]:
    video = session.get(m.Video, video_id)
    if video is None:
        raise ProblemError(404, "VIDEO_NOT_FOUND", "Video no encontrado")
    if video.video_type not in ("LONG", "SHORT"):
        # Un tipo ambiguo no se mezcla con largos ni Shorts (spec §0.5).
        raise ProblemError(
            422,
            "VIDEO_TYPE_UNCLEAR",
            "El tipo del video no está confirmado",
            "Solo se anotan videos LONG o SHORT confirmados.",
        )
    opp, _created = ensure_opportunity(
        session,
        niche_id=niche_id,
        format_id=format_id,
        target_lang="es",
        video_type=video.video_type,
    )
    annotation = m.VideoAnnotation(
        id=str(uuid4()),
        video_id=video.id,
        opportunity_id=opp.id,
        same_format_confidence=confidence,
        label_source="HUMAN",
        model_version=None,
        prompt_version=None,
        rationale=rationale,
        reviewed_by=reviewer,
    )
    session.add(annotation)
    langs = list(opp.source_languages_json)
    if video.language_state not in ("UNKNOWN", "") and video.language_state not in langs:
        opp.source_languages_json = [*langs, video.language_state]
    session.flush()
    return annotation, opp


# --- fuentes permitidas y planes --------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    source_id: str
    kind: str
    title: str | None
    channel: str | None
    language: str | None


def allowed_evidence(session: Session, opportunity_id: str) -> list[EvidenceItem]:
    """Todo lo que el modelo puede citar. Cualquier otro source_id se rechaza (T13)."""
    items: dict[str, EvidenceItem] = {}
    opp = session.get(m.Opportunity, opportunity_id)
    if opp is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    niche = session.get(m.Niche, opp.niche_id)
    items[f"O:{opp.id}"] = EvidenceItem(
        f"O:{opp.id}",
        "OPPORTUNITY",
        f"{niche.canonical_name_es if niche else ''}",
        None,
        opp.target_lang,
    )
    for ev in session.scalars(
        select(m.OpportunityEvidence).where(m.OpportunityEvidence.opportunity_id == opp.id)
    ).all():
        if ev.entity_type == "VIDEO":
            video = session.scalars(
                select(m.Video).where(m.Video.youtube_video_id == ev.entity_id)
            ).first()
            channel = session.get(m.Channel, video.channel_id) if video else None
            items[f"V:{ev.entity_id}"] = EvidenceItem(
                f"V:{ev.entity_id}",
                "VIDEO",
                video.title if video else None,
                channel.title_current if channel else None,
                video.language_state if video else None,
            )
        elif ev.entity_type == "CHANNEL":
            channel = session.scalars(
                select(m.Channel).where(m.Channel.youtube_channel_id == ev.entity_id)
            ).first()
            items[f"C:{ev.entity_id}"] = EvidenceItem(
                f"C:{ev.entity_id}",
                "CHANNEL",
                None,
                channel.title_current if channel else None,
                None,
            )
    for ann in session.scalars(
        select(m.VideoAnnotation).where(m.VideoAnnotation.opportunity_id == opp.id)
    ).all():
        video = session.get(m.Video, ann.video_id)
        if video is None:
            continue
        channel = session.get(m.Channel, video.channel_id)
        items[f"V:{video.youtube_video_id}"] = EvidenceItem(
            f"V:{video.youtube_video_id}",
            "VIDEO",
            video.title,
            channel.title_current if channel else None,
            video.language_state,
        )
    return list(items.values())


def _check_sources(session: Session, opportunity_id: str, source_ids: list[str]) -> None:
    allowed = {e.source_id for e in allowed_evidence(session, opportunity_id)}
    unknown = [s for s in source_ids if s not in allowed]
    if unknown:
        raise ProblemError(
            422,
            "INVALID_EVIDENCE_REF",
            "El plan cita fuentes que no existen",
            f"Referencias no válidas: {', '.join(unknown[:5])}",
        )


def plan_out_dict(plan: m.SpanishSearchPlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "opportunity_id": plan.opportunity_id,
        "status": plan.status,
        "origin": plan.origin,
        "plan": plan.plan_json,
        "prompt_version": plan.prompt_version,
        "model_version": plan.model_version,
        "error_code": plan.error_code,
        "approved_by": plan.approved_by,
        "approved_at": plan.approved_at,
        "created_at": plan.created_at,
    }


def create_manual_plan(
    session: Session, opportunity_id: str, draft: SpanishSearchPlan
) -> m.SpanishSearchPlan:
    _check_sources(session, opportunity_id, draft.source_ids)
    plan = m.SpanishSearchPlan(
        id=str(uuid4()),
        opportunity_id=opportunity_id,
        status="PENDING_REVIEW",
        origin="HUMAN",
        plan_json=draft.model_dump(),
        prompt_version=None,
        model_version=None,
        source_ids_json=draft.source_ids,
        error_code=None,
        approved_by=None,
        approved_at=None,
    )
    session.add(plan)
    session.flush()
    return plan


def generate_plan_with_ai(
    session: Session, client: AIClient, opportunity_id: str
) -> m.SpanishSearchPlan:
    """Pide el plan a la IA. Si no pasa la validación, queda NEEDS_REVIEW sin hechos."""
    opp = session.get(m.Opportunity, opportunity_id)
    if opp is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    niche = session.get(m.Niche, opp.niche_id)
    fmt = session.get(m.Format, opp.format_id)
    evidence = allowed_evidence(session, opportunity_id)
    user = prompt_v1.build_user_message(
        {
            "nicho": niche.canonical_name_es if niche else "",
            "definicion_nicho": niche.definition if niche else "",
            "formato": fmt.canonical_name_es if fmt else "",
            "estructura_formato": fmt.story_structure if fmt else "",
            "idioma_destino": opp.target_lang,
            "tipo_video": opp.video_type,
        },
        [
            {
                "source_id": e.source_id,
                "tipo": e.kind,
                "titulo": e.title,
                "canal": e.channel,
                "idioma": e.language,
            }
            for e in evidence
        ],
    )
    raw = client.complete(prompt_v1.SYSTEM, user)
    plan = m.SpanishSearchPlan(
        id=str(uuid4()),
        opportunity_id=opportunity_id,
        status="NEEDS_REVIEW",
        origin="AI",
        plan_json={},
        prompt_version=prompt_v1.PROMPT_VERSION,
        model_version=client.model,
        source_ids_json=[],
        error_code=None,
        approved_by=None,
        approved_at=None,
    )
    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        plan.error_code = "INVALID_JSON"
        session.add(plan)
        session.flush()
        return plan
    try:
        draft = SpanishSearchPlan.model_validate(data)
    except ValidationError:
        plan.error_code = "INVALID_PLAN"
        session.add(plan)
        session.flush()
        return plan
    allowed = {e.source_id for e in evidence}
    if any(s not in allowed for s in draft.source_ids):
        plan.error_code = "INVALID_EVIDENCE_REF"
        session.add(plan)
        session.flush()
        return plan
    plan.status = "PENDING_REVIEW"
    plan.plan_json = draft.model_dump()
    plan.source_ids_json = draft.source_ids
    session.add(plan)
    session.flush()
    return plan


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    return stripped.strip()


def update_plan(
    session: Session, plan_id: str, draft: SpanishSearchPlan, *, approve: bool, reviewer: str
) -> m.SpanishSearchPlan:
    plan = session.get(m.SpanishSearchPlan, plan_id)
    if plan is None:
        raise ProblemError(404, "PLAN_NOT_FOUND", "Plan no encontrado")
    if plan.status == "APPROVED" or plan.status == "SUPERSEDED":
        raise ProblemError(
            409, "PLAN_LOCKED", "Un plan aprobado no se edita; cree una versión nueva"
        )
    _check_sources(session, plan.opportunity_id, draft.source_ids)
    plan.plan_json = draft.model_dump()
    plan.source_ids_json = draft.source_ids
    plan.error_code = None
    if approve:
        others = session.scalars(
            select(m.SpanishSearchPlan).where(
                m.SpanishSearchPlan.opportunity_id == plan.opportunity_id,
                m.SpanishSearchPlan.status == "APPROVED",
            )
        ).all()
        for other in others:
            other.status = "SUPERSEDED"
        plan.status = "APPROVED"
        plan.approved_by = reviewer
        plan.approved_at = datetime.now(UTC)
    else:
        plan.status = "PENDING_REVIEW"
    session.flush()
    return plan


def approved_plan(session: Session, plan_id: str, opportunity_id: str) -> m.SpanishSearchPlan:
    plan = session.get(m.SpanishSearchPlan, plan_id)
    if plan is None or plan.opportunity_id != opportunity_id:
        raise ProblemError(404, "PLAN_NOT_FOUND", "Plan no encontrado para esta oportunidad")
    if plan.status != "APPROVED":
        raise ProblemError(
            409, "PLAN_NOT_APPROVED", "Solo se valida con un plan aprobado por una persona"
        )
    return plan


def plan_queries(plan: m.SpanishSearchPlan) -> list[tuple[str, str]]:
    return query_texts(SpanishSearchPlan.model_validate(plan.plan_json))


# --- coberura, evaluación y revisión ----------------------------------------------------------


def coverage_for(session: Session, opportunity_id: str) -> spanish_market.SpanishCoverage:
    queries = session.scalars(
        select(m.SourceQuery).where(
            m.SourceQuery.opportunity_id == opportunity_id,
            m.SourceQuery.status == "OK",
            m.SourceQuery.provider == "youtube_official",
        )
    ).all()
    matches = session.scalars(
        select(m.DiscoveryMatch).where(
            m.DiscoveryMatch.opportunity_id == opportunity_id,
            m.DiscoveryMatch.is_spanish_market.is_(True),
        )
    ).all()
    # Se cuenta por video único: un mismo video hallado por dos búsquedas es un solo competidor.
    es_videos = {mt.video_id for mt in matches}
    reviewed = {mt.video_id for mt in matches if mt.match_quality != "UNREVIEWED"}
    exact = {mt.video_id for mt in matches if mt.match_quality == "EXACT"}
    return spanish_market.SpanishCoverage(
        queries_run=len(queries),
        query_variants=len({q.query_text.lower() for q in queries}),
        es_verified_videos=len(es_videos),
        reviewed_matches=len(reviewed),
        exact_matches=len(exact),
    )


def min_review_share() -> float:
    research = load_research_config(get_settings().research_config_path)["research"]
    return float(research.get("spanish_review_min_share", spanish_market.MIN_REVIEW_SHARE))


def ai_assist_stats(session: Session, opportunity_id: str) -> dict[str, Any]:
    """Cuántas sugerencias de la IA hay y cuánto coinciden con la revisión humana."""
    rows = session.execute(
        select(
            m.DiscoveryMatch.video_id,
            m.DiscoveryMatch.match_quality,
            m.DiscoveryMatch.ai_quality,
            m.DiscoveryMatch.reviewed_by,
        )
        .where(
            m.DiscoveryMatch.opportunity_id == opportunity_id,
            m.DiscoveryMatch.is_spanish_market.is_(True),
            m.DiscoveryMatch.ai_quality.is_not(None),
        )
        .order_by(m.DiscoveryMatch.video_id)
    ).all()
    suggested: dict[str, str] = {}
    individual: dict[str, str] = {}  # revisados uno a uno: miden la precisión de la IA
    in_bulk: set[str] = set()  # aceptados en bloque: coinciden por construcción
    for video_id, quality, ai_quality, reviewed_by in rows:
        suggested.setdefault(video_id, str(ai_quality))
        if quality == "UNREVIEWED":
            continue
        if str(reviewed_by or "").endswith("(aceptó sugerencia IA)"):
            in_bulk.add(video_id)
        else:
            individual.setdefault(video_id, str(quality))
    agreed = sum(1 for vid, quality in individual.items() if suggested.get(vid) == quality)
    return {
        "videos_with_suggestion": len(suggested),
        "reviewed_individually": len(individual),
        "accepted_in_bulk": len(in_bulk),
        "agreed": agreed,
        "agreement": None if not individual else round(agreed / len(individual), 3),
    }


def small_channel_access(session: Session, opportunity_id: str) -> dict[str, Any]:
    """Éxito accesible a canales pequeños, medido sobre los competidores exactos revisados.

    Es una métrica derivada de datos de la API: solo se calcula con la compuerta abierta.
    """
    settings = get_settings()
    if not decide("derived_metrics", settings, session).allowed:
        return {"state": "RESTRICTED", "ratio": None, "rule_version": "small-access-v1"}
    research = load_research_config(settings.research_config_path)["research"]
    rows = session.execute(
        select(m.Video, m.Channel)
        .join(m.DiscoveryMatch, m.DiscoveryMatch.video_id == m.Video.id)
        .join(m.Channel, m.Channel.id == m.Video.channel_id)
        .where(
            m.DiscoveryMatch.opportunity_id == opportunity_id,
            m.DiscoveryMatch.match_quality == "EXACT",
            m.DiscoveryMatch.is_spanish_market.is_(True),
            m.Video.availability != "EXPIRED",
        )
    ).all()
    return small_channel_access_domain.assess(
        [
            small_channel_access_domain.ExactCompetitor(
                video_id=video.youtube_video_id,
                channel_id=channel.youtube_channel_id,
                view_count=video.view_count,
                subscriber_count=channel.subscriber_count,
            )
            for video, channel in rows
        ],
        success_min_views=int(research.get("long_video_views_soft_min", 50_000)),
        small_max_subscribers=int(research.get("candidate_channel_subscribers_soft_max", 50_000)),
    )


def record_assessment(
    session: Session, opportunity_id: str, run_id: str | None, now: datetime
) -> dict[str, Any]:
    """Añade una evaluación nueva con el estado español recalculado (append-only)."""
    coverage = coverage_for(session, opportunity_id)
    settings = get_settings()
    demand = demand_state.summary(session, settings, opportunity_id, now)
    result = spanish_market.assess(
        coverage,
        independent_signals=int(demand["independent_signals"]),
        min_review_share=min_review_share(),
    )
    spanish = {
        "saturation_state": result.saturation_state,
        "spanish_demand_state": result.demand_state,
        "entry_decision": result.entry_decision,
        "query_coverage_count": coverage.queries_run,
        "query_variants": coverage.query_variants,
        "es_verified_videos": coverage.es_verified_videos,
        "reviewed_matches": coverage.reviewed_matches,
        "exact_matches": coverage.exact_matches,
        "match_precision_reviewed": coverage.reviewed_matches > 0,
        "review_coverage": {
            "es_verified_videos": coverage.es_verified_videos,
            "reviewed_videos": coverage.reviewed_matches,
            "share": spanish_market.review_share(coverage),
            "min_share": min_review_share(),
        },
        "ai_assist": ai_assist_stats(session, opportunity_id),
        "small_channel_access": small_channel_access(session, opportunity_id),
        "demand_signals": demand,
        "reason_codes": result.reason_codes,
    }
    evaluation_service.append_evaluation(
        session,
        opportunity_id,
        now=now,
        source="OFFICIAL",
        run_id=run_id,
        spanish=spanish,
        confidence=result.confidence,
    )
    opp = session.get(m.Opportunity, opportunity_id)
    if opp is not None:
        opp.status = ENTRY_TO_STATUS.get(result.entry_decision, "ES_VALIDATION_IN_PROGRESS")
    session.flush()
    return spanish


def review_match(session: Session, match_id: str, quality: str, reviewer: str) -> m.DiscoveryMatch:
    if quality not in MATCH_QUALITIES:
        raise ProblemError(422, "INVALID_QUALITY", "Calidad de coincidencia no válida")
    match = session.get(m.DiscoveryMatch, match_id)
    if match is None:
        raise ProblemError(404, "MATCH_NOT_FOUND", "Coincidencia no encontrada")
    # La decisión es sobre el video: se aplica a todas las búsquedas que lo encontraron.
    siblings = session.scalars(
        select(m.DiscoveryMatch).where(
            m.DiscoveryMatch.video_id == match.video_id,
            m.DiscoveryMatch.opportunity_id == match.opportunity_id,
        )
    ).all()
    for sibling in siblings or [match]:
        sibling.match_quality = quality
        sibling.reviewed_by = reviewer
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=match.run_id,
            actor=reviewer,
            event_type="MATCH_REVIEWED",
            object_type="discovery_match",
            object_id=match.id,
            details_redacted_json={"match_quality": quality},
        )
    )
    session.flush()
    if match.opportunity_id is not None:
        record_assessment(session, match.opportunity_id, match.run_id, datetime.now(UTC))
    return match


def competition(session: Session, opportunity_id: str) -> list[dict[str, Any]]:
    """Un renglón por video: la revisión es sobre el video, no sobre cada búsqueda que lo halló."""
    rows = session.execute(
        select(m.DiscoveryMatch, m.Video, m.Channel, m.SourceQuery)
        .join(m.Video, m.Video.id == m.DiscoveryMatch.video_id)
        .join(m.Channel, m.Channel.id == m.Video.channel_id)
        .join(m.SourceQuery, m.SourceQuery.id == m.DiscoveryMatch.query_id)
        .where(m.DiscoveryMatch.opportunity_id == opportunity_id)
        .order_by(m.DiscoveryMatch.position, m.DiscoveryMatch.id)
    ).all()
    grouped: dict[str, dict[str, Any]] = {}
    for match, video, channel, query in rows:
        entry = grouped.get(match.video_id)
        if entry is None:
            grouped[match.video_id] = {
                "id": match.id,
                "video_title": video.title,
                "channel_title": channel.title_current,
                "video_language": video.language_state,
                "is_spanish_market": match.is_spanish_market,
                "match_quality": match.match_quality,
                "query": query.query_text,
                "queries_count": 1,
                "query_language": query.language_requested,
                "region": query.region,
                "position": match.position,
                "run_id": match.run_id,
                "ai_quality": match.ai_quality,
                "ai_confidence": match.ai_confidence,
                "ai_reason": match.ai_reason,
            }
        else:
            entry["queries_count"] += 1
            if match.ai_quality and not entry["ai_quality"]:
                entry.update(
                    ai_quality=match.ai_quality,
                    ai_confidence=match.ai_confidence,
                    ai_reason=match.ai_reason,
                )
    order = {"UNREVIEWED": 0, "EXACT": 1, "ADJACENT": 2, "GENERIC": 3, "FALSE_POSITIVE": 4}
    return sorted(
        grouped.values(),
        key=lambda r: (
            not r["is_spanish_market"],
            order.get(str(r["match_quality"]), 9),
            int(r["position"]),
        ),
    )
