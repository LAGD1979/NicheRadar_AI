from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.schemas import (
    CapabilityOut,
    CompareRequest,
    CompareResponse,
    ConfigPublic,
    OpportunityDetail,
    OpportunityItem,
    Page,
    ProviderOut,
    RunAccepted,
    RunCreate,
    RunOut,
    VideoItem,
)
from app.core.config import Settings, get_settings
from app.core.errors import ProblemError
from app.core.research_config import load_research_config
from app.db import models as m
from app.db.session import get_session
from app.domain.rules import age_hours
from app.services import opportunity_service as opp_svc
from app.services.compliance_service import all_decisions, decide
from app.services.providers_service import list_providers
from app.services.research_service import enqueue_demo_run, get_run

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/config/public", response_model=ConfigPublic)
def config_public(settings: SettingsDep) -> ConfigPublic:
    research = load_research_config(settings.research_config_path)
    r = research["research"]
    q = research["quota"]
    return ConfigPublic(
        app_env=settings.app_env,
        demo_mode=settings.demo_mode,
        synthetic_banner=settings.demo_mode,
        compliance_mode=settings.compliance_mode,
        advanced_analytics_enabled=False,
        target_language=r["target_language"],
        lookback_days=r["lookback_days"],
        spanish_regions=r["spanish_regions"],
        languages=r["languages"],
        quota_soft_caps={
            "youtube_search_daily": q["youtube_search_daily_soft_cap"],
            "youtube_other_daily": q["youtube_other_daily_soft_cap"],
            "reserve_spanish_pct": q["reserve_spanish_pct"],
            "ai_run_usd": q["ai_run_usd_soft_cap"],
        },
        timezone=research["ui"]["timezone"],
        secrets_configured={
            "youtube_api_key": bool(settings.youtube_api_key.get_secret_value()),
            "anthropic_api_key": bool(settings.anthropic_api_key.get_secret_value()),
            "openai_api_key": bool(settings.openai_api_key.get_secret_value()),
        },
    )


@router.get("/providers", response_model=list[ProviderOut])
def providers(settings: SettingsDep) -> list[ProviderOut]:
    return list_providers(settings)


@router.get("/policy/capabilities", response_model=list[CapabilityOut])
def capabilities(settings: SettingsDep) -> list[CapabilityOut]:
    return [
        CapabilityOut(
            id=d.capability,
            label=d.label,
            allowed=d.allowed,
            state=d.state,
            reason=d.reason,
        )
        for d in all_decisions(settings)
    ]


@router.get("/opportunities", response_model=Page[OpportunityItem])
def list_opportunities(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(max_length=40)] = None,
    video_type: Annotated[str | None, Query(max_length=10)] = None,
    confidence: Annotated[str | None, Query(max_length=20)] = None,
    saturation_es: Annotated[str | None, Query(max_length=20)] = None,
    spanish_demand_state: Annotated[str | None, Query(max_length=30)] = None,
    entry_decision: Annotated[str | None, Query(max_length=40)] = None,
    replication_state: Annotated[str | None, Query(max_length=30)] = None,
    faceless_state: Annotated[str | None, Query(max_length=30)] = None,
    rights_risk: Annotated[str | None, Query(max_length=20)] = None,
    sort: Annotated[str, Query(max_length=20)] = "name",
) -> Page[OpportunityItem]:
    filters = {
        "status": status,
        "video_type": video_type,
        "confidence": confidence,
        "saturation_es": saturation_es,
        "spanish_demand_state": spanish_demand_state,
        "entry_decision": entry_decision,
        "replication_state": replication_state,
        "faceless_state": faceless_state,
        "rights_risk": rights_risk,
    }
    items, total = opp_svc.list_opportunities(
        session,
        page=page,
        page_size=page_size,
        q=q,
        filters={k: v for k, v in filters.items() if v},
        sort=opp_svc.parse_sort(sort),
    )
    return Page[OpportunityItem](items=items, page=page, page_size=page_size, total=total)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityDetail)
def opportunity_detail(
    opportunity_id: str, session: SessionDep, settings: SettingsDep
) -> OpportunityDetail:
    return opp_svc.get_opportunity_detail(session, settings, opportunity_id)


@router.get("/opportunities/{opportunity_id}/scores")
def opportunity_scores(settings: SettingsDep) -> None:
    """Puntuaciones compuestas: bloqueadas en restricted (T17). Sin bypass por frontend.

    Si la compuerta se abriera (M4), aquí se calcularía el score; en M0 nunca se alcanza.
    """
    decision = decide("advanced_scores", settings)
    if not decision.allowed:
        raise ProblemError(403, "POLICY_RESTRICTED", "Puntuación no habilitada", decision.reason)
    raise ProblemError(501, "NOT_IMPLEMENTED", "Cálculo de scores pendiente de M4")


@router.post("/compare", response_model=CompareResponse)
def compare(body: CompareRequest, session: SessionDep, settings: SettingsDep) -> CompareResponse:
    return opp_svc.compare(session, settings, body.opportunity_ids)


@router.get("/videos", response_model=Page[VideoItem])
def list_videos(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=100)] = None,
    video_type: Annotated[str | None, Query(max_length=10)] = None,
    language_state: Annotated[str | None, Query(max_length=20)] = None,
) -> Page[VideoItem]:
    stmt = select(m.Video, m.Channel).join(m.Channel, m.Channel.id == m.Video.channel_id)
    if q:
        stmt = stmt.where(
            or_(
                m.Video.title.icontains(q, autoescape=True),
                m.Channel.title_current.icontains(q, autoescape=True),
            )
        )
    if video_type:
        stmt = stmt.where(m.Video.video_type == video_type)
    if language_state:
        stmt = stmt.where(m.Video.language_state == language_state)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(
        stmt.order_by(m.Video.published_at.desc(), m.Video.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        VideoItem(
            id=v.id,
            youtube_video_id=v.youtube_video_id,
            title=v.title,
            channel_title=c.title_current,
            subscriber_band=c.subscriber_band,
            published_at=v.published_at,
            age_hours=_age_or_none(v.published_at, v.observed_at),
            duration_seconds=v.duration_seconds,
            video_type=v.video_type,
            video_type_evidence=v.video_type_evidence,
            language_state=v.language_state,
            language_confidence=v.language_confidence,
            view_count=v.view_count,
            url=v.url,
            provider=v.provider,
            observed_at=v.observed_at,
            source_data_type=v.source_data_type,
            availability=v.availability,
        )
        for v, c in rows
    ]
    return Page[VideoItem](items=items, page=page, page_size=page_size, total=int(total))


def _age_or_none(published_at: Any, observed_at: Any) -> float | None:
    try:
        return age_hours(published_at, observed_at)
    except ValueError:
        return None


def _run_out(run: m.ResearchRun) -> RunOut:
    return RunOut(
        id=run.id,
        kind=run.kind,
        status=run.status,
        algorithm_version=run.algorithm_version,
        policy_mode=run.policy_mode,
        started_at=run.started_at,
        finished_at=run.finished_at,
        params=run.params_json,
        coverage=run.coverage_json,
        errors=run.errors_json,
        budget=run.budget_json,
    )


@router.get("/research-runs", response_model=Page[RunOut])
def list_runs(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[RunOut]:
    total = session.scalar(select(func.count()).select_from(m.ResearchRun)) or 0
    runs = session.scalars(
        select(m.ResearchRun)
        .order_by(m.ResearchRun.created_at.desc(), m.ResearchRun.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[RunOut](
        items=[_run_out(r) for r in runs],
        page=page,
        page_size=page_size,
        total=int(total),
    )


@router.get("/research-runs/{run_id}", response_model=RunOut)
def run_detail(run_id: str, session: SessionDep) -> RunOut:
    return _run_out(get_run(session, run_id))


@router.post("/research-runs", response_model=RunAccepted, status_code=202)
def create_run(body: RunCreate, session: SessionDep, settings: SettingsDep) -> RunAccepted:
    """Encola la corrida y responde 202: el trabajo lo ejecuta el worker, no el request."""
    run = enqueue_demo_run(session, settings.compliance_mode)
    session.commit()
    return RunAccepted(id=run.id, kind=run.kind, status=run.status)
