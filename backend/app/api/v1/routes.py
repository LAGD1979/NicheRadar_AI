from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.m2_routes import router as m2_router
from app.api.v1.m3_routes import router as m3_router
from app.api.v1.schemas import (
    CapabilityOut,
    ChannelOut,
    CompareRequest,
    CompareResponse,
    ConfigPublic,
    DiscoveryPayload,
    ImportRequest,
    ImportSummary,
    OpportunityDetail,
    OpportunityItem,
    Page,
    ProviderOut,
    RunAccepted,
    RunCreate,
    RunOut,
    UsageOut,
    VideoItem,
)
from app.core.config import Settings, get_settings
from app.core.errors import ProblemError
from app.core.research_config import load_research_config
from app.db import models as m
from app.db.session import get_session
from app.domain.rules import age_hours
from app.services import opportunity_service as opp_svc
from app.services import quota_service
from app.services.compliance_service import all_decisions, decide
from app.services.import_service import import_rows
from app.services.providers_service import list_providers
from app.services.research_service import (
    enqueue_run,
    get_run,
    resume_run,
    run_events,
)

router = APIRouter()
router.include_router(m2_router)
router.include_router(m3_router)

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UNIT_COST_SEARCH = 100


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
            "youtube_units_daily_budget": quota_service.daily_budget(settings),
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


@router.get("/usage", response_model=UsageOut)
def usage(session: SessionDep, settings: SettingsDep) -> UsageOut:
    return UsageOut(**quota_service.snapshot(session, settings, datetime.now(UTC)))


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

    Si la compuerta se abriera (M4), aquí se calcularía el score; en M1 nunca se alcanza.
    """
    decision = decide("advanced_scores", settings)
    if not decision.allowed:
        raise ProblemError(403, "POLICY_RESTRICTED", "Puntuación no habilitada", decision.reason)
    raise ProblemError(501, "NOT_IMPLEMENTED", "Cálculo de scores pendiente de M4")


@router.post("/compare", response_model=CompareResponse)
def compare(body: CompareRequest, session: SessionDep, settings: SettingsDep) -> CompareResponse:
    return opp_svc.compare(session, settings, body.opportunity_ids)


def _age_or_none(published_at: Any, observed_at: Any) -> float | None:
    try:
        return age_hours(published_at, observed_at)
    except ValueError:
        return None


def _video_item(v: m.Video, c: m.Channel) -> VideoItem:
    return VideoItem(
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
        owner_authorized=v.owner_authorized,
        retention_deadline=v.retention_deadline,
        last_refreshed_at=v.last_refreshed_at,
    )


@router.get("/videos", response_model=Page[VideoItem])
def list_videos(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=100)] = None,
    video_type: Annotated[str | None, Query(max_length=10)] = None,
    language_state: Annotated[str | None, Query(max_length=20)] = None,
    source_data_type: Annotated[str | None, Query(max_length=20)] = None,
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
    if source_data_type:
        stmt = stmt.where(m.Video.source_data_type == source_data_type)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(
        stmt.order_by(m.Video.published_at.desc(), m.Video.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_video_item(v, c) for v, c in rows]
    return Page[VideoItem](items=items, page=page, page_size=page_size, total=int(total))


@router.get("/channels/{channel_id}", response_model=ChannelOut)
def channel_detail(channel_id: str, session: SessionDep) -> ChannelOut:
    channel = session.scalars(
        select(m.Channel).where(
            or_(m.Channel.id == channel_id, m.Channel.youtube_channel_id == channel_id)
        )
    ).first()
    if channel is None:
        raise ProblemError(404, "CHANNEL_NOT_FOUND", "Canal no encontrado")
    video_count = (
        session.scalar(
            select(func.count()).select_from(m.Video).where(m.Video.channel_id == channel.id)
        )
        or 0
    )
    return ChannelOut(
        id=channel.id,
        youtube_channel_id=channel.youtube_channel_id,
        title=channel.title_current,
        subscriber_count=channel.subscriber_count,
        subscriber_band=channel.subscriber_band,
        uploads_playlist_id=channel.uploads_playlist_id,
        provider=channel.provider,
        observed_at=channel.observed_at,
        source_data_type=channel.source_data_type,
        owner_authorized=channel.owner_authorized,
        retention_deadline=channel.retention_deadline,
        last_refreshed_at=channel.last_refreshed_at,
        video_count=int(video_count),
    )


@router.post("/imports/provider-file", response_model=ImportSummary)
def import_provider_file(
    body: ImportRequest, session: SessionDep, settings: SettingsDep
) -> ImportSummary:
    """Importa CSV/JSON exportado con derecho de reutilización. Errores por fila; idempotente."""
    summary = import_rows(
        session,
        settings,
        provider=body.provider,
        idempotency_key=body.idempotency_key,
        license_confirmed=body.license_confirmed,
        source_schema_version=body.source_schema_version,
        rows=body.rows,
        csv_text=body.csv_text,
    )
    session.commit()
    return ImportSummary(**summary)


def _run_out(session: Session, run: m.ResearchRun) -> RunOut:
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
        events=run_events(session, run.id),
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
        items=[_run_out(session, r) for r in runs],
        page=page,
        page_size=page_size,
        total=int(total),
    )


@router.get("/research-runs/{run_id}", response_model=RunOut)
def run_detail(run_id: str, session: SessionDep) -> RunOut:
    return _run_out(session, get_run(session, run_id))


def _discovery_budget(payload: DiscoveryPayload) -> dict[str, Any]:
    return {
        "max_search_calls": payload.max_search_calls,
        "youtube_units_estimate": payload.max_search_calls * UNIT_COST_SEARCH,
        "ai_usd": 0,
    }


@router.post("/research-runs", response_model=RunAccepted, status_code=202)
def create_run(body: RunCreate, session: SessionDep, settings: SettingsDep) -> RunAccepted:
    """Encola la corrida y responde 202. El worker la ejecuta; el request no espera."""
    if body.kind == "demo":
        run = enqueue_run(
            session,
            kind="demo",
            policy_mode=settings.compliance_mode,
            payload={"dataset": "synthetic_v1"},
            params={"dataset": "synthetic_v1", "network": False},
            algorithm_version="m0-demo-1",
            budget={"youtube_units": 0, "ai_usd": 0},
        )
    elif body.kind == "discovery":
        if body.payload is None:
            raise ProblemError(
                422, "PAYLOAD_REQUIRED", "La búsqueda necesita queries y presupuesto"
            )
        if not settings.youtube_api_key.get_secret_value():
            raise ProblemError(
                409,
                "PROVIDER_NOT_CONFIGURED",
                "YouTube no está configurado",
                "Defina YOUTUBE_API_KEY y reinicie la API y el worker.",
            )
        payload = body.payload.model_dump()
        run = enqueue_run(
            session,
            kind="discovery",
            policy_mode=settings.compliance_mode,
            payload=payload,
            params={
                "queries_total": len(payload["queries"]),
                "pages_per_query": payload["pages_per_query"],
                "max_search_calls": payload["max_search_calls"],
            },
            algorithm_version="m1-ingest-1",
            budget=_discovery_budget(body.payload),
        )
    else:
        run = enqueue_run(
            session,
            kind="purge",
            policy_mode=settings.compliance_mode,
            payload={},
            params={"purge": "retention"},
            algorithm_version="m1-purge-1",
            budget={},
        )
    session.commit()
    return RunAccepted(id=run.id, kind=run.kind, status=run.status)


@router.post("/research-runs/{run_id}/resume", response_model=RunAccepted, status_code=202)
def resume(run_id: str, session: SessionDep) -> RunAccepted:
    run = resume_run(session, run_id)
    session.commit()
    return RunAccepted(id=run.id, kind=run.kind, status=run.status)
