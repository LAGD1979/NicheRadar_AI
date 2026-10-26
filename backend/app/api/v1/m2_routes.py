"""Rutas del mercado español (M2): taxonomía, anotaciones, planes, validación y revisión."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ProblemError
from app.db import models as m
from app.db.session import get_session
from app.domain import spanish_market
from app.domain.search_plan import SpanishSearchPlan
from app.services import (
    ai_selection_service,
    competitor_ai_service,
    replication_service,
    spanish_service,
)
from app.services.research_service import enqueue_run

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Window = Literal["0-7", "8-30", "31-90"]


class OpportunityCreate(BaseModel):
    niche_id: str = Field(min_length=1, max_length=36)
    format_id: str = Field(min_length=1, max_length=36)
    video_type: Literal["LONG", "SHORT"] = "LONG"
    target_lang: Literal["es"] = "es"


class AnnotationCreate(BaseModel):
    niche_id: str = Field(min_length=1, max_length=36)
    format_id: str = Field(min_length=1, max_length=36)
    same_format_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    rationale: str = Field(min_length=10, max_length=1000)


class PlanUpdate(BaseModel):
    plan: SpanishSearchPlan
    approve: bool = False


class ValidationRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=36)
    windows: list[Window] = Field(min_length=1, max_length=3)
    max_search_calls: int = Field(default=10, ge=1, le=80)
    pages_per_query: int = Field(default=1, ge=1, le=2)


class MatchReview(BaseModel):
    match_quality: Literal["UNREVIEWED", "EXACT", "ADJACENT", "GENERIC", "FALSE_POSITIVE"]


@router.get("/taxonomy")
def taxonomy(session: SessionDep) -> dict[str, Any]:
    niches = session.scalars(select(m.Niche).order_by(m.Niche.canonical_name_es)).all()
    formats = session.scalars(select(m.Format).order_by(m.Format.canonical_name_es)).all()
    return {
        "niches": [
            {"id": n.id, "name": n.canonical_name_es, "definition": n.definition} for n in niches
        ],
        "formats": [{"id": f.id, "name": f.canonical_name_es} for f in formats],
    }


class NicheCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    definition: str = Field(min_length=20, max_length=1000)


class FormatCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    story_structure: str = Field(min_length=20, max_length=1000)
    visual_grammar: str = Field(default="", max_length=1000)
    audio_grammar: str = Field(default="", max_length=1000)


def _clean(value: str) -> str:
    if any(ord(ch) < 32 for ch in value):
        raise ProblemError(422, "INVALID_TEXT", "El texto contiene caracteres de control")
    return value.strip()


@router.post("/taxonomy/niches", status_code=201)
def create_niche(body: NicheCreate, session: SessionDep) -> dict[str, Any]:
    """Nicho definido por una persona. Un nombre repetido (sin distinguir mayúsculas) se rechaza."""
    name = _clean(body.name)
    clash = session.scalars(
        select(m.Niche).where(func.lower(m.Niche.canonical_name_es) == name.lower())
    ).first()
    if clash is not None:
        raise ProblemError(409, "NICHE_EXISTS", "Ya existe un nicho con ese nombre", clash.id)
    niche = m.Niche(
        id=str(uuid4()),
        canonical_name_es=name,
        definition=_clean(body.definition),
        exclusions_json=[],
        taxonomy_version="user-v1",
        source_data_type="HUMAN",
    )
    session.add(niche)
    session.commit()
    return {"id": niche.id, "name": niche.canonical_name_es, "definition": niche.definition}


@router.post("/taxonomy/formats", status_code=201)
def create_format(body: FormatCreate, session: SessionDep) -> dict[str, Any]:
    name = _clean(body.name)
    clash = session.scalars(
        select(m.Format).where(func.lower(m.Format.canonical_name_es) == name.lower())
    ).first()
    if clash is not None:
        raise ProblemError(409, "FORMAT_EXISTS", "Ya existe un formato con ese nombre", clash.id)
    fmt = m.Format(
        id=str(uuid4()),
        canonical_name_es=name,
        story_structure=_clean(body.story_structure),
        visual_grammar=_clean(body.visual_grammar),
        audio_grammar=_clean(body.audio_grammar),
        min_assets=None,
        requirements_json={},
        taxonomy_version="user-v1",
        source_data_type="HUMAN",
    )
    session.add(fmt)
    session.commit()
    return {"id": fmt.id, "name": fmt.canonical_name_es}


@router.post("/opportunities", status_code=201)
def create_opportunity(body: OpportunityCreate, session: SessionDep) -> dict[str, Any]:
    opp, created = spanish_service.ensure_opportunity(
        session,
        niche_id=body.niche_id,
        format_id=body.format_id,
        target_lang=body.target_lang,
        video_type=body.video_type,
    )
    session.commit()
    return {"id": opp.id, "created": created}


@router.post("/videos/{video_id}/annotations", status_code=201)
def annotate(
    video_id: str, body: AnnotationCreate, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Etiqueta humana: el video pertenece a un nicho y formato. Crea la oportunidad si falta.

    Si la política lo permite, recalcula la replicación internacional de la oportunidad.
    """
    annotation, opp = spanish_service.annotate_video(
        session,
        video_id=video_id,
        niche_id=body.niche_id,
        format_id=body.format_id,
        confidence=body.same_format_confidence,
        rationale=body.rationale,
        reviewer="local_owner",
    )
    replication = replication_service.refresh(session, settings, opp.id, datetime.now(UTC))
    session.commit()
    return {
        "annotation_id": annotation.id,
        "opportunity_id": opp.id,
        "replication_state": replication.get("state"),
    }


@router.post("/opportunities/{opportunity_id}/replication/refresh")
def refresh_replication(
    opportunity_id: str, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Recalcula la replicación con los videos agrupados vigentes (caducados no cuentan)."""
    if session.get(m.Opportunity, opportunity_id) is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    replication = replication_service.refresh(session, settings, opportunity_id, datetime.now(UTC))
    session.commit()
    if replication.get("state") == "RESTRICTED":
        raise ProblemError(
            403, "POLICY_RESTRICTED", "La replicación está restringida", replication.get("reason")
        )
    return replication


@router.get("/opportunities/{opportunity_id}/search-plans")
def list_plans(opportunity_id: str, session: SessionDep) -> list[dict[str, Any]]:
    plans = session.scalars(
        select(m.SpanishSearchPlan)
        .where(m.SpanishSearchPlan.opportunity_id == opportunity_id)
        .order_by(m.SpanishSearchPlan.created_at.desc(), m.SpanishSearchPlan.id)
    ).all()
    return [spanish_service.plan_out_dict(p) for p in plans]


@router.post("/opportunities/{opportunity_id}/search-plans", status_code=201)
def create_manual_plan(
    opportunity_id: str, body: SpanishSearchPlan, session: SessionDep
) -> dict[str, Any]:
    """Plan escrito por una persona. Queda pendiente de aprobación."""
    plan = spanish_service.create_manual_plan(session, opportunity_id, body)
    session.commit()
    return spanish_service.plan_out_dict(plan)


@router.post(
    "/opportunities/{opportunity_id}/search-plans/generate", response_model=None, status_code=202
)
def generate_plan(
    opportunity_id: str, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    if not ai_selection_service.configured(session, settings, "plan"):
        raise ProblemError(
            409,
            "AI_NOT_CONFIGURED",
            "La IA no está configurada",
            "Defina AI_PROVIDER=anthropic, ANTHROPIC_API_KEY y AI_MODEL, y reinicie el worker.",
        )
    if session.get(m.Opportunity, opportunity_id) is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    run = enqueue_run(
        session,
        kind="spanish_plan",
        policy_mode=settings.compliance_mode,
        payload={"opportunity_id": opportunity_id},
        params={
            "opportunity_id": opportunity_id,
            "model": ai_selection_service.selection(session, settings, "plan")["model"],
        },
        algorithm_version="m2-plan-1",
        budget={"ai_usd_cap": settings.ai_max_usd_per_run},
    )
    session.commit()
    return {"id": run.id, "kind": run.kind, "status": run.status}


@router.patch("/search-plans/{plan_id}")
def update_plan(plan_id: str, body: PlanUpdate, session: SessionDep) -> dict[str, Any]:
    plan = spanish_service.update_plan(
        session, plan_id, body.plan, approve=body.approve, reviewer="local_owner"
    )
    session.commit()
    return spanish_service.plan_out_dict(plan)


@router.post("/opportunities/{opportunity_id}/validate-spanish", status_code=202)
def validate_spanish(
    opportunity_id: str, body: ValidationRequest, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    if not settings.youtube_api_key.get_secret_value():
        raise ProblemError(
            409,
            "PROVIDER_NOT_CONFIGURED",
            "YouTube no está configurado",
            "Defina YOUTUBE_API_KEY y reinicie la API y el worker.",
        )
    spanish_service.approved_plan(session, body.plan_id, opportunity_id)
    run = enqueue_run(
        session,
        kind="spanish_validation",
        policy_mode=settings.compliance_mode,
        payload={
            "opportunity_id": opportunity_id,
            "plan_id": body.plan_id,
            "windows": body.windows,
            "max_search_calls": body.max_search_calls,
            "pages_per_query": body.pages_per_query,
        },
        params={"opportunity_id": opportunity_id, "plan_id": body.plan_id, "windows": body.windows},
        algorithm_version="m2-es-1",
        budget={
            "max_search_calls": body.max_search_calls,
            "youtube_units_estimate": body.max_search_calls * 100,
        },
    )
    session.commit()
    return {"id": run.id, "kind": run.kind, "status": run.status}


@router.get("/opportunities/{opportunity_id}/competition")
def competition(opportunity_id: str, session: SessionDep) -> dict[str, Any]:
    if session.get(m.Opportunity, opportunity_id) is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    coverage = spanish_service.coverage_for(session, opportunity_id)
    return {
        "coverage": {
            "queries_run": coverage.queries_run,
            "query_variants": coverage.query_variants,
            "es_verified_videos": coverage.es_verified_videos,
            "reviewed_matches": coverage.reviewed_matches,
            "exact_matches": coverage.exact_matches,
            "review_share": spanish_market.review_share(coverage),
            "min_review_share": spanish_service.min_review_share(),
            "ai_pending": competitor_ai_service.pending_count(session, opportunity_id),
        },
        "ai_assist": spanish_service.ai_assist_stats(session, opportunity_id),
        "matches": spanish_service.competition(session, opportunity_id),
    }


class AcceptAI(BaseModel):
    min_confidence: Literal["HIGH", "MEDIUM"] = "HIGH"


@router.post("/opportunities/{opportunity_id}/competition/ai-review", status_code=202)
def request_ai_review(
    opportunity_id: str, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Encola la clasificación asistida: la IA propone, una persona acepta o corrige."""
    if not ai_selection_service.configured(session, settings, "classification"):
        raise ProblemError(
            409,
            "AI_NOT_CONFIGURED",
            "La IA no está configurada",
            "Defina AI_PROVIDER, la clave del proveedor y AI_MODEL, y reinicie el worker.",
        )
    if session.get(m.Opportunity, opportunity_id) is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    pending = competitor_ai_service.pending_count(session, opportunity_id)
    if pending == 0:
        raise ProblemError(
            409,
            "NO_PENDING_MATCHES",
            "No hay competidores en español pendientes de sugerencia",
            "Todos están revisados o ya tienen una sugerencia de la IA.",
        )
    run = enqueue_run(
        session,
        kind="match_review",
        policy_mode=settings.compliance_mode,
        payload={"opportunity_id": opportunity_id},
        params={
            "opportunity_id": opportunity_id,
            "model": ai_selection_service.selection(session, settings, "classification")["model"],
            "pending": pending,
        },
        algorithm_version="match-review-1",
        budget={
            "ai_usd_cap": settings.ai_max_usd_per_run,
            "batches_estimate": -(-pending // competitor_ai_service.BATCH_SIZE),
        },
    )
    session.commit()
    return {"id": run.id, "kind": run.kind, "status": run.status, "pending": pending}


@router.post("/opportunities/{opportunity_id}/competition/accept-ai")
def accept_ai(opportunity_id: str, body: AcceptAI, session: SessionDep) -> dict[str, Any]:
    """Acción humana: acepta en bloque las sugerencias con la confianza indicada."""
    if session.get(m.Opportunity, opportunity_id) is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    result = competitor_ai_service.accept_suggestions(
        session,
        opportunity_id,
        min_confidence=body.min_confidence,
        reviewer="local_owner",
        now=datetime.now(UTC),
    )
    session.commit()
    return result


@router.patch("/matches/{match_id}")
def review(match_id: str, body: MatchReview, session: SessionDep) -> dict[str, Any]:
    """Revisión humana: EXACT, ADJACENT, GENERIC o FALSE_POSITIVE. Recalcula el estado español."""
    match = spanish_service.review_match(
        session, match_id, body.match_quality, reviewer="local_owner"
    )
    session.commit()
    return {"id": match.id, "match_quality": match.match_quality, "reviewed_by": match.reviewed_by}


@router.get("/search-plans/{plan_id}")
def get_plan(plan_id: str, session: SessionDep) -> dict[str, Any]:
    plan = session.get(m.SpanishSearchPlan, plan_id)
    if plan is None:
        raise ProblemError(404, "PLAN_NOT_FOUND", "Plan no encontrado")
    return spanish_service.plan_out_dict(plan)
