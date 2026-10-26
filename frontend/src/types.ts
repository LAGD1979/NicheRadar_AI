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
  recommendation: string | null;
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
  retention_deadline: string | null;
  provider_metrics: { vidiq?: VidiqMetrics } | null;
  opportunities: Array<{ id: string; label: string }>;
}

export interface VidiqMetrics {
  breakout_score: number | null;
  views_per_hour: number | null;
  engagement_rate: number | null;
  trend_categories: string[];
  observed_at: string;
}

export interface VidiqUsage {
  provider: string;
  quota_bucket: string;
  day_start_utc: string;
  credits_used: number;
  credits_daily_limit: number;
  credits_remaining: number;
}

export interface Taxonomy {
  niches: Array<{ id: string; name: string; definition: string }>;
  formats: Array<{ id: string; name: string }>;
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

export interface SearchPlanBody {
  schema_version: "1.0";
  canonical_concept_es: string;
  same_format_definition: string;
  query_groups: Array<{ region: string; language: string; queries: string[]; exclusions: string[] }>;
  adjacent_but_distinct: string[];
  localization_notes: string[];
  source_ids: string[];
}

export interface SearchPlan {
  id: string;
  opportunity_id: string;
  status: string;
  origin: string;
  plan: Partial<SearchPlanBody>;
  prompt_version: string | null;
  model_version: string | null;
  error_code: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface CompetitionMatch {
  id: string;
  video_title: string;
  channel_title: string;
  video_language: string;
  is_spanish_market: boolean;
  match_quality: string;
  query: string;
  query_language: string;
  region: string | null;
  position: number;
  run_id: string;
}

export interface Competition {
  coverage: {
    queries_run: number;
    query_variants: number;
    es_verified_videos: number;
    reviewed_matches: number;
    exact_matches: number;
  };
  matches: CompetitionMatch[];
}

export interface CostModelOut {
  version: number;
  params: {
    duration_minutes: number;
    words_per_minute: number;
    planned_words: number;
    lines: Array<{
      name: string;
      unit: string;
      quantity: number;
      prices: Record<string, number | null>;
    }>;
  };
  scenarios: { usd_per_video: Record<string, number | null>; currency: string; estimated: boolean };
  missing: Record<string, string[]>;
  created_by: string;
  created_at: string;
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
