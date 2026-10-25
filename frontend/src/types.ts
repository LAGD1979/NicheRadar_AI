// Tipos que reflejan backend/app/api/v1/schemas.py. Se mantienen a mano en M0;
// la generación desde OpenAPI llega cuando el contrato se estabilice.

export type FieldState = "AVAILABLE" | "NOT_AVAILABLE" | "RESTRICTED";

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  warnings: string[];
}

export interface OpportunityItem {
  id: string;
  niche: string;
  format: string;
  target_lang: string;
  video_type: string;
  status: string;
  confidence: string | null;
  replication_state: string | null;
  saturation_es: string | null;
  spanish_demand_state: string | null;
  entry_decision: string | null;
  faceless_state: string | null;
  complexity_1_to_5: number | null;
  rights_risk: string | null;
  observed_at: string | null;
  data_source: string;
}

export interface ScoreOut {
  value: number | null;
  state: FieldState;
  reason: string | null;
}

export interface EvidenceOut {
  id: string;
  market: string;
  role: string;
  entity_type: string;
  entity_id: string;
  title: string | null;
  channel_title: string | null;
  evidence_text: string;
  source: string;
  observed_at: string;
  support_strength: string;
  availability: string;
}

export interface EvaluationOut {
  evaluation_version: number;
  confidence: string;
  reason_codes: string[];
  recommendation: string;
  metric_policy_state: string;
  international: Record<string, unknown>;
  spanish: Record<string, unknown>;
  feasibility: Record<string, unknown>;
  scores: Record<string, ScoreOut>;
  data_source: string;
  observed_at: string;
  run_id: string | null;
}

export interface OpportunityDetail {
  id: string;
  niche: { id: string; name: string; definition: string; exclusions: string[] };
  format: {
    id: string;
    name: string;
    story_structure: string;
    visual_grammar: string;
    audio_grammar: string;
    min_assets: number | null;
  };
  target_lang: string;
  video_type: string;
  status: string;
  owner_notes: string | null;
  source_languages: string[];
  evaluation: EvaluationOut | null;
  evidence: EvidenceOut[];
}

export interface FieldDef {
  key: string;
  label: string;
  group: string;
}

export interface FieldValue {
  value: unknown;
  state: FieldState;
  source: string | null;
  observed_at: string | null;
  reason: string | null;
}

export interface CompareItem {
  id: string;
  title: string;
  values: Record<string, FieldValue>;
}

export interface CompareResponse {
  fields: FieldDef[];
  items: CompareItem[];
}

export interface VideoItem {
  id: string;
  youtube_video_id: string;
  title: string;
  channel_title: string;
  subscriber_band: string;
  published_at: string;
  age_hours: number | null;
  duration_seconds: number | null;
  video_type: string;
  video_type_evidence: string;
  language_state: string;
  language_confidence: string;
  view_count: number | null;
  url: string | null;
  provider: string;
  observed_at: string;
  source_data_type: string;
  availability: string;
}

export interface RunOut {
  id: string;
  kind: string;
  status: string;
  algorithm_version: string;
  policy_mode: string;
  started_at: string | null;
  finished_at: string | null;
  params: Record<string, unknown>;
  coverage: Record<string, unknown>;
  errors: Array<Record<string, unknown>>;
  budget: Record<string, unknown>;
  events?: Array<{ event_type: string; actor: string; created_at: string | null }>;
}

export interface UsageOut {
  provider: string;
  quota_bucket: string;
  day_start_utc: string;
  resets_at_utc: string;
  units_used: number;
  units_budget_soft: number;
  units_limit_hard: number;
  units_remaining_soft: number;
}

export interface ProviderOut {
  id: string;
  name: string;
  enabled: boolean;
  status: string;
  license_note: string;
}

export interface CapabilityOut {
  id: string;
  label: string;
  allowed: boolean;
  state: string;
  reason: string;
}

export interface ConfigPublic {
  app_env: string;
  demo_mode: boolean;
  synthetic_banner: boolean;
  compliance_mode: string;
  advanced_analytics_enabled: boolean;
  target_language: string;
  lookback_days: number;
  spanish_regions: string[];
  languages: string[];
  quota_soft_caps: Record<string, number>;
  timezone: string;
  secrets_configured: Record<string, boolean>;
}

export interface ProblemBody {
  code?: string;
  title?: string;
  detail?: string | null;
  request_id?: string | null;
}
