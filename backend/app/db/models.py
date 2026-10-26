from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Niche(Base):
    __tablename__ = "niches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_name_es: Mapped[str] = mapped_column(String(200))
    definition: Mapped[str] = mapped_column(Text)
    exclusions_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    taxonomy_version: Mapped[str] = mapped_column(String(40))
    source_data_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Format(Base):
    __tablename__ = "formats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_name_es: Mapped[str] = mapped_column(String(200))
    story_structure: Mapped[str] = mapped_column(Text)
    visual_grammar: Mapped[str] = mapped_column(Text)
    audio_grammar: Mapped[str] = mapped_column(Text)
    min_assets: Mapped[int | None] = mapped_column(Integer)
    requirements_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    taxonomy_version: Mapped[str] = mapped_column(String(40))
    source_data_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    youtube_channel_id: Mapped[str] = mapped_column(String(64), unique=True)
    title_current: Mapped[str] = mapped_column(String(200))
    # NULL = suscriptores no visibles; 0 = cero real. Nunca se confunden (T02).
    subscriber_count: Mapped[int | None] = mapped_column(Integer)
    subscriber_band: Mapped[str] = mapped_column(String(40))
    language_state: Mapped[str] = mapped_column(String(20))
    region_declared: Mapped[str | None] = mapped_column(String(10))
    provider: Mapped[str] = mapped_column(String(60))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str | None] = mapped_column(String(36))
    source_data_type: Mapped[str] = mapped_column(String(20))
    uploads_playlist_id: Mapped[str | None] = mapped_column(String(64))
    owner_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        Index("ix_videos_published_type_lang", "published_at", "video_type", "language_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    youtube_video_id: Mapped[str] = mapped_column(String(64), unique=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    title: Mapped[str] = mapped_column(String(300))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    video_type: Mapped[str] = mapped_column(String(10))
    video_type_evidence: Mapped[str] = mapped_column(String(200))
    language_state: Mapped[str] = mapped_column(String(20))
    language_confidence: Mapped[str] = mapped_column(String(20))
    view_count: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(300))
    # Métricas de proveedor con procedencia por clave ({"vidiq": {...}}). Se purgan con el video.
    provider_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(String(60))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str | None] = mapped_column(String(36))
    source_data_type: Mapped[str] = mapped_column(String(20))
    availability: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    owner_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceQuery(Base):
    """Búsqueda exacta ejecutada (sin claves). Permite auditar qué produjo cada video."""

    __tablename__ = "source_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    language_requested: Mapped[str] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(10))
    query_text: Mapped[str] = mapped_column(String(300))
    window_code: Mapped[str] = mapped_column(String(10))
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))
    warnings_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)


class DiscoveryMatch(Base):
    """Un video encontrado por una búsqueda. Un mismo video puede tener varios matches (T01)."""

    __tablename__ = "discovery_matches"
    __table_args__ = (UniqueConstraint("query_id", "video_id", name="uq_discovery_match"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    query_id: Mapped[str] = mapped_column(ForeignKey("source_queries.id"))
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(40))
    match_quality: Mapped[str] = mapped_column(String(20), default="UNREVIEWED")
    is_spanish_market: Mapped[bool] = mapped_column(Boolean, default=False)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120))


class DemandObservation(Base):
    """Una medida de demanda en español de una fuente externa. Caduca a los 29 días (D-63)."""

    __tablename__ = "demand_observations"
    __table_args__ = (Index("ix_demand_obs_opportunity", "opportunity_id", "family"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"))
    family: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(40))
    keyword: Mapped[str] = mapped_column(String(200))
    geo: Mapped[str | None] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str] = mapped_column(String(60))
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str | None] = mapped_column(String(36))
    source_data_type: Mapped[str] = mapped_column(String(20), default="PROVIDER")
    availability: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    retention_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VideoAnnotation(Base):
    """Etiqueta de un video para un nicho y formato. Solo cuenta si tiene evidencia y autor."""

    __tablename__ = "video_annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    same_format_confidence: Mapped[str] = mapped_column(String(10))
    label_source: Mapped[str] = mapped_column(String(20))
    model_version: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpanishSearchPlan(Base):
    """Plan de búsqueda en español. Versionado; solo un plan APPROVED por oportunidad."""

    __tablename__ = "spanish_search_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(10))
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    model_version: Mapped[str | None] = mapped_column(String(60))
    source_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(60))
    approved_by: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CostModel(Base):
    """Modelo de costo por video. Versión nueva en cada cambio; sin precio, el total es NULL."""

    __tablename__ = "cost_models"
    __table_args__ = (UniqueConstraint("opportunity_id", "version", name="uq_cost_model_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scenarios_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    missing_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProviderUsage(Base):
    """Unidades de cuota consumidas por llamada. El día de cuota se calcula en Pacific Time."""

    __tablename__ = "provider_usage"
    __table_args__ = (
        Index("ix_provider_usage_bucket_time", "provider", "quota_bucket", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(36))
    provider: Mapped[str] = mapped_column(String(60))
    endpoint: Mapped[str] = mapped_column(String(40))
    quota_bucket: Mapped[str] = mapped_column(String(40))
    units: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint(
            "niche_id", "format_id", "target_lang", "video_type", name="uq_opportunity_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    niche_id: Mapped[str] = mapped_column(ForeignKey("niches.id"))
    format_id: Mapped[str] = mapped_column(ForeignKey("formats.id"))
    target_lang: Mapped[str] = mapped_column(String(10), default="es")
    video_type: Mapped[str] = mapped_column(String(10), default="LONG")
    source_languages_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(40))
    owner_notes: Mapped[str | None] = mapped_column(Text)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpportunityEvidence(Base):
    __tablename__ = "opportunity_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(40))
    evidence_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    support_strength: Mapped[str] = mapped_column(String(20))
    availability: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    source_data_type: Mapped[str] = mapped_column(String(20))


class Evaluation(Base):
    """Evaluación append-only por versión. Campos no observados quedan en NULL."""

    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "evaluation_version", name="uq_evaluation_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("research_runs.id"))
    evaluation_version: Mapped[int] = mapped_column(Integer)
    international_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spanish_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    feasibility_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scores_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confidence: Mapped[str] = mapped_column(String(20))
    reason_codes_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    recommendation: Mapped[str] = mapped_column(String(40))
    metric_policy_state: Mapped[str] = mapped_column(String(40))
    source_data_type: Mapped[str] = mapped_column(String(20))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    algorithm_version: Mapped[str] = mapped_column(String(20))
    policy_mode: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    errors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunTask(Base):
    __tablename__ = "run_tasks"
    __table_args__ = (
        UniqueConstraint("run_id", "dedupe_key", name="uq_run_task_dedupe"),
        Index("ix_run_tasks_queue", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"))
    task_type: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_class: Mapped[str | None] = mapped_column(String(60))


class PolicyApproval(Base):
    __tablename__ = "policy_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(60))
    capability: Mapped[str] = mapped_column(String(60))
    scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    approval_ref: Mapped[str | None] = mapped_column(String(200))
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(36))
    actor: Mapped[str] = mapped_column(String(60))
    event_type: Mapped[str] = mapped_column(String(60))
    object_type: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str] = mapped_column(String(64))
    details_redacted_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
