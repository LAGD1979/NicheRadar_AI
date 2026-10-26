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

export interface DemandSignal {
  family: string;
  state: string;
  reason: string;
  keyword?: string;
  geo?: string | null;
  provider?: string;
  observed_at?: string;
  expires_at?: string | null;
  details?: Record<string, unknown>;
}

export interface DemandSummary {
  independent_signals: number;
  present_families: string[];
  family_states: Record<string, string>;
  signals: DemandSignal[];
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
  queries_count: number;
  ai_quality: string | null;
  ai_confidence: string | null;
  ai_reason: string | null;
}

export interface AiAssistStats {
  videos_with_suggestion: number;
  reviewed_individually: number;
  accepted_in_bulk: number;
  agreed: number;
  agreement: number | null;
}

export interface Competition {
  coverage: {
    queries_run: number;
    query_variants: number;
    es_verified_videos: number;
    reviewed_matches: number;
    exact_matches: number;
    review_share: number | null;
    min_review_share: number;
    ai_pending: number;
  };
  ai_assist: AiAssistStats;
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
  data_mode: "SYNTHETIC" | "MIXED" | "REAL";
  real_video_count: number;
  synthetic_video_count: number;
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

export interface AssistantStatus {
  configured: boolean;
  provider: string;
  model: string | null;
  messages_used_today: number;
  messages_daily_limit: number;
  messages_remaining: number;
}

export interface AssistantContext {
  context: Record<string, unknown>;
  sections: string[];
  tokens_estimate: number;
}

export interface AssistantAnswer {
  answer: string;
  citations: string[];
  unknowns: string[];
  next_steps: string[];
  structured: boolean;
  unsourced: boolean;
  model: string;
  context_tokens_estimate: number;
  messages_remaining: number;
}

export interface AssistantTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AiModelOption {
  provider: string;
  model: string;
  label: string;
  description: string;
  available: boolean;
}

export interface AiFunctionSetting {
  id: string;
  label: string;
  description: string;
  suggestion: string;
  provider: string;
  model: string | null;
  source: "user" | "default";
  configured: boolean;
}

export interface AiSettings {
  functions: AiFunctionSetting[];
  catalog: AiModelOption[];
  default: { provider: string; model: string | null };
}

export interface SchedulerJob {
  job_type: string;
  label: string;
  description: string;
  enabled: boolean;
  interval_hours: number;
  next_run_at: string;
  last_run_at: string | null;
  last_run_id: string | null;
  last_status: string | null;
}

export interface AlertItem {
  id: string;
  alert_type: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  opportunity_id: string | null;
  message: string;
  created_at: string;
  acknowledged_at: string | null;
}

export interface AlertsOut {
  open: number;
  critical: number;
  items: AlertItem[];
}

export interface PilotPlan {
  hypothesis: string;
  proposed_videos: string[];
  success_metrics: string;
}

export interface WatchChange {
  key: string;
  before: string | number | null;
  after: string | number | null;
}

export interface WatchEntry {
  opportunity_id: string;
  niche: string | null;
  format: string | null;
  video_type: string;
  status: string;
  priority: "LOW" | "MEDIUM" | "HIGH";
  notes: string | null;
  pilot_plan: Partial<PilotPlan>;
  next_review_at: string;
  review_overdue: boolean;
  snapshot_at: string;
  changes: WatchChange[];
  open_alerts: number;
  last_action: { action: string; reason: string | null; actor: string; created_at: string } | null;
}
