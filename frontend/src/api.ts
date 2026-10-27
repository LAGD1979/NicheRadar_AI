import type {
  AiFunctionSetting,
  AiUsage,
  AlertItem,
  AlertsOut,
  PilotPlan,
  BackupList,
  SchedulerJob,
  WatchEntry,
  AiSettings,
  AssistantAnswer,
  AssistantContext,
  AssistantStatus,
  AssistantTurn,
  CapabilityOut,
  CompareResponse,
  DemandSummary,
  ConfigPublic,
  OpportunityDetail,
  OpportunityItem,
  Page,
  ProblemBody,
  ProviderOut,
  Competition,
  CostModelOut,
  RunOut,
  SearchPlan,
  Taxonomy,
  UsageOut,
  VideoItem,
  VidiqUsage,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { Accept: "application/json", "Content-Type": "application/json" },
  });
  if (!response.ok) {
    let problem: ProblemBody = {};
    try {
      problem = (await response.json()) as ProblemBody;
    } catch {
      // Respuesta sin cuerpo JSON: se usa el código HTTP.
    }
    throw new ApiError(
      response.status,
      problem.code ?? `HTTP_${String(response.status)}`,
      problem.title ?? response.statusText,
      problem.request_id ?? null,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  config: () => request<ConfigPublic>("/config/public"),
  providers: () => request<ProviderOut[]>("/providers"),
  capabilities: () => request<CapabilityOut[]>("/policy/capabilities"),
  opportunities: (params: URLSearchParams) =>
    request<Page<OpportunityItem>>(`/opportunities?${params.toString()}`),
  opportunity: (id: string) =>
    request<OpportunityDetail>(`/opportunities/${encodeURIComponent(id)}`),
  compare: (ids: string[]) =>
    request<CompareResponse>("/compare", {
      method: "POST",
      body: JSON.stringify({ opportunity_ids: ids }),
    }),
  videos: (params: URLSearchParams) => request<Page<VideoItem>>(`/videos?${params.toString()}`),
  runs: () => request<Page<RunOut>>("/research-runs?page_size=20"),
  createDemoRun: () =>
    request<{ id: string; kind: string; status: string }>("/research-runs", {
      method: "POST",
      body: JSON.stringify({ kind: "demo" }),
    }),
  createRun: (body: unknown) =>
    request<{ id: string; kind: string; status: string }>("/research-runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resumeRun: (id: string) =>
    request<{ id: string; kind: string; status: string }>(
      `/research-runs/${encodeURIComponent(id)}/resume`,
      { method: "POST" },
    ),
  usage: () => request<UsageOut>("/usage"),
  vidiqUsage: () => request<VidiqUsage>("/usage/vidiq"),
  taxonomy: () => request<Taxonomy>("/taxonomy"),
  createNiche: (body: { name: string; definition: string }) =>
    request<{ id: string; name: string }>("/taxonomy/niches", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createFormat: (body: { name: string; story_structure: string; visual_grammar: string }) =>
    request<{ id: string; name: string }>("/taxonomy/formats", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  annotateVideo: (
    videoId: string,
    body: { niche_id: string; format_id: string; same_format_confidence: string; rationale: string },
  ) =>
    request<{ annotation_id: string; opportunity_id: string }>(
      `/videos/${encodeURIComponent(videoId)}/annotations`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  plans: (opportunityId: string) =>
    request<SearchPlan[]>(`/opportunities/${encodeURIComponent(opportunityId)}/search-plans`),
  createManualPlan: (opportunityId: string, plan: unknown) =>
    request<SearchPlan>(`/opportunities/${encodeURIComponent(opportunityId)}/search-plans`, {
      method: "POST",
      body: JSON.stringify(plan),
    }),
  generatePlan: (opportunityId: string) =>
    request<{ id: string; kind: string; status: string }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/search-plans/generate`,
      { method: "POST" },
    ),
  updatePlan: (planId: string, body: { plan: unknown; approve: boolean }) =>
    request<SearchPlan>(`/search-plans/${encodeURIComponent(planId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  validateSpanish: (opportunityId: string, body: unknown) =>
    request<{ id: string; kind: string; status: string }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/validate-spanish`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  competition: (opportunityId: string) =>
    request<Competition>(`/opportunities/${encodeURIComponent(opportunityId)}/competition`),
  costModel: (opportunityId: string) =>
    request<CostModelOut>(`/opportunities/${encodeURIComponent(opportunityId)}/cost-model`),
  saveCostModel: (opportunityId: string, body: unknown) =>
    request<{ version: number }>(`/opportunities/${encodeURIComponent(opportunityId)}/cost-model`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  saveFeasibility: (opportunityId: string, body: unknown) =>
    request<{ evaluation_version: number; recommendation: string; gates: string[] }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/feasibility`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  demand: (opportunityId: string) =>
    request<DemandSummary>(`/opportunities/${encodeURIComponent(opportunityId)}/demand`),
  requestDemand: (
    opportunityId: string,
    body: { keywords: string[]; geo: string | null; sources: string[]; include_related: boolean; force?: boolean },
  ) =>
    request<{ id: string; status: string; budget: Record<string, number> }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/demand`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  requestHistory: (opportunityId: string, maxCalls: number) =>
    request<{ id: string; status: string; budget: Record<string, number> }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/temporal-resilience`,
      { method: "POST", body: JSON.stringify({ max_calls: maxCalls }) },
    ),
  schedulerJobs: () => request<SchedulerJob[]>("/scheduler/jobs"),
  backups: () => request<BackupList>("/backups"),
  updateJob: (jobType: string, body: { enabled?: boolean; interval_hours?: number }) =>
    request<SchedulerJob>(`/scheduler/jobs/${jobType}`, { method: "PATCH", body: JSON.stringify(body) }),
  runJob: (jobType: string) =>
    request<{ id: string }>(`/scheduler/jobs/${jobType}/run`, { method: "POST" }),
  alerts: (includeAcknowledged = false) =>
    request<AlertsOut>(`/alerts?include_acknowledged=${String(includeAcknowledged)}`),
  acknowledgeAlert: (id: string) =>
    request<AlertItem>(`/alerts/${id}/acknowledge`, { method: "POST" }),
  acknowledgeAllAlerts: () =>
    request<{ acknowledged: number }>("/alerts/acknowledge-all", { method: "POST" }),
  watchlist: () => request<WatchEntry[]>("/watchlist"),
  watch: (opportunityId: string, priority: string, notes: string | null) =>
    request<WatchEntry>(`/opportunities/${opportunityId}/watch`, {
      method: "POST",
      body: JSON.stringify({ priority, notes }),
    }),
  updateWatch: (
    opportunityId: string,
    body: { priority?: string; notes?: string; next_review_at?: string; pilot_plan?: PilotPlan },
  ) =>
    request<WatchEntry>(`/watchlist/${opportunityId}`, { method: "PATCH", body: JSON.stringify(body) }),
  reviewedWatch: (opportunityId: string, reviewDays: number) =>
    request<WatchEntry>(`/watchlist/${opportunityId}/reviewed`, {
      method: "POST",
      body: JSON.stringify({ review_days: reviewDays }),
    }),
  removeWatch: (opportunityId: string, reason: string) =>
    request<{ status: string }>(`/watchlist/${opportunityId}/remove`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  aiUsage: () => request<AiUsage>("/usage/ai"),
  aiSettings: () => request<AiSettings>("/ai/settings"),
  setAiSetting: (fn: string, provider: string, model: string) =>
    request<AiFunctionSetting>(`/ai/settings/${fn}`, {
      method: "PUT",
      body: JSON.stringify({ provider, model }),
    }),
  clearAiSetting: (fn: string) => request<AiFunctionSetting>(`/ai/settings/${fn}`, { method: "DELETE" }),
  assistantStatus: () => request<AssistantStatus>("/assistant/status"),
  assistantContext: (opportunityId: string) =>
    request<AssistantContext>(`/opportunities/${opportunityId}/assistant/context`),
  assistantAsk: (opportunityId: string, message: string, history: AssistantTurn[]) =>
    request<AssistantAnswer>(`/opportunities/${opportunityId}/assistant`, {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),
  hasdataUsage: () =>
    request<{
      calls_used: number;
      calls_daily_limit: number;
      calls_remaining: number;
      calls_month_used: number;
      calls_monthly_limit: number;
      calls_month_remaining: number;
    }>("/usage/hasdata"),
  saveEditorial: (
    opportunityId: string,
    body: {
      differentiation: string;
      differentiation_reason: string;
      maintainability: string;
      maintainability_reason: string;
    },
  ) =>
    request<{ evaluation_version: number }>(`/opportunities/${encodeURIComponent(opportunityId)}/editorial`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  requestAiReview: (opportunityId: string) =>
    request<{ id: string; status: string; pending: number }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/competition/ai-review`,
      { method: "POST" },
    ),
  acceptAiSuggestions: (opportunityId: string, minConfidence: "HIGH" | "MEDIUM") =>
    request<{ accepted: number; by_quality: Record<string, number>; left_for_manual_review: number }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/competition/accept-ai`,
      { method: "POST", body: JSON.stringify({ min_confidence: minConfidence }) },
    ),
  reviewMatch: (matchId: string, matchQuality: string) =>
    request<{ id: string; match_quality: string }>(`/matches/${encodeURIComponent(matchId)}`, {
      method: "PATCH",
      body: JSON.stringify({ match_quality: matchQuality }),
    }),
};
