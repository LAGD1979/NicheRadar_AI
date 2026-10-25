from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    warnings: list[str] = Field(default_factory=list)


class ScoreOut(BaseModel):
    value: float | None
    state: Literal["AVAILABLE", "NOT_AVAILABLE", "RESTRICTED"]
    reason: str | None = None


class NicheOut(BaseModel):
    id: str
    name: str
    definition: str
    exclusions: list[str]


class FormatOut(BaseModel):
    id: str
    name: str
    story_structure: str
    visual_grammar: str
    audio_grammar: str
    min_assets: int | None


class OpportunityItem(BaseModel):
    id: str
    recommendation: str | None = None
    niche: str
    format: str
    target_lang: str
    video_type: str
    status: str
    confidence: str | None
    replication_state: str | None
    saturation_es: str | None
    spanish_demand_state: str | None
    entry_decision: str | None
    faceless_state: str | None
    complexity_1_to_5: int | None
    rights_risk: str | None
    observed_at: datetime | None
    data_source: str


class EvidenceOut(BaseModel):
    id: str
    market: str
    role: str
    entity_type: str
    entity_id: str
    title: str | None
    channel_title: str | None
    evidence_text: str
    source: str
    observed_at: datetime
    support_strength: str
    availability: str


class EvaluationOut(BaseModel):
    evaluation_version: int
    confidence: str
    reason_codes: list[str]
    recommendation: str
    metric_policy_state: str
    international: dict[str, Any]
    spanish: dict[str, Any]
    feasibility: dict[str, Any]
    scores: dict[str, ScoreOut]
    data_source: str
    observed_at: datetime
    run_id: str | None


class OpportunityDetail(BaseModel):
    id: str
    niche: NicheOut
    format: FormatOut
    target_lang: str
    video_type: str
    status: str
    owner_notes: str | None
    source_languages: list[str]
    evaluation: EvaluationOut | None
    evidence: list[EvidenceOut]


class CompareRequest(BaseModel):
    opportunity_ids: list[str] = Field(min_length=2, max_length=8)


class FieldDef(BaseModel):
    key: str
    label: str
    group: str


class FieldValue(BaseModel):
    value: Any
    state: Literal["AVAILABLE", "NOT_AVAILABLE", "RESTRICTED"]
    source: str | None
    observed_at: datetime | None
    reason: str | None = None


class CompareItem(BaseModel):
    id: str
    title: str
    values: dict[str, FieldValue]


class CompareResponse(BaseModel):
    fields: list[FieldDef]
    items: list[CompareItem]


class VideoItem(BaseModel):
    id: str
    youtube_video_id: str
    title: str
    channel_title: str
    subscriber_band: str
    published_at: datetime
    age_hours: float | None
    duration_seconds: int | None
    video_type: str
    video_type_evidence: str
    language_state: str
    language_confidence: str
    view_count: int | None
    url: str | None
    provider: str
    observed_at: datetime
    source_data_type: str
    availability: str
    owner_authorized: bool
    retention_deadline: datetime | None
    last_refreshed_at: datetime | None


class ChannelOut(BaseModel):
    id: str
    youtube_channel_id: str
    title: str
    subscriber_count: int | None
    subscriber_band: str
    uploads_playlist_id: str | None
    provider: str
    observed_at: datetime
    source_data_type: str
    owner_authorized: bool
    retention_deadline: datetime | None
    last_refreshed_at: datetime | None
    video_count: int


class QuerySpec(BaseModel):
    language: str = Field(pattern=r"^[a-z]{2,3}(-(Hans|Hant|[A-Z]{2}))?$", max_length=12)
    query: str = Field(min_length=2, max_length=200)
    window: Literal["0-7", "8-30", "31-90"]
    region: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class DiscoveryPayload(BaseModel):
    queries: list[QuerySpec] = Field(min_length=1, max_length=50)
    max_search_calls: int = Field(default=10, ge=1, le=80)
    pages_per_query: int = Field(default=1, ge=1, le=3)


class ImportRequest(BaseModel):
    source_schema_version: str = Field(max_length=10)
    provider: Literal["vidiq_import", "manual_import"]
    idempotency_key: str = Field(min_length=1, max_length=80)
    license_confirmed: bool
    rows: list[dict[str, Any]] | None = Field(default=None, max_length=5000)
    csv_text: str | None = Field(default=None, max_length=5_000_000)


class ImportError(BaseModel):
    row: int
    field: str
    message: str


class ImportSummary(BaseModel):
    provider: str
    idempotency_key: str
    source_schema_version: str
    received: int
    accepted: int
    rejected: int
    errors: list[ImportError]
    idempotent_replay: bool


class UsageOut(BaseModel):
    provider: str
    quota_bucket: str
    day_start_utc: str
    resets_at_utc: str
    units_used: int
    units_budget_soft: int
    units_limit_hard: int
    units_remaining_soft: int


class RunOut(BaseModel):
    id: str
    kind: str
    status: str
    algorithm_version: str
    policy_mode: str
    started_at: datetime | None
    finished_at: datetime | None
    params: dict[str, Any]
    coverage: dict[str, Any]
    errors: list[dict[str, Any]]
    budget: dict[str, Any]
    events: list[dict[str, Any]] = Field(default_factory=list)


class RunCreate(BaseModel):
    kind: Literal["demo", "discovery", "purge"]
    payload: DiscoveryPayload | None = None


class RunAccepted(BaseModel):
    id: str
    kind: str
    status: str


class ProviderOut(BaseModel):
    id: str
    name: str
    enabled: bool
    status: Literal["CONFIGURED", "NOT_CONFIGURED", "DISABLED", "SYNTHETIC"]
    license_note: str


class CapabilityOut(BaseModel):
    id: str
    label: str
    allowed: bool
    state: str
    reason: str


class ConfigPublic(BaseModel):
    app_env: str
    demo_mode: bool
    synthetic_banner: bool
    compliance_mode: str
    advanced_analytics_enabled: bool
    target_language: str
    lookback_days: int
    spanish_regions: list[str]
    languages: list[str]
    quota_soft_caps: dict[str, int]
    timezone: str
    secrets_configured: dict[str, bool]
