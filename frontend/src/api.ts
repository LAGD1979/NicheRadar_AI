import type {
  CapabilityOut,
  CompareResponse,
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
  reviewMatch: (matchId: string, matchQuality: string) =>
    request<{ id: string; match_quality: string }>(`/matches/${encodeURIComponent(matchId)}`, {
      method: "PATCH",
      body: JSON.stringify({ match_quality: matchQuality }),
    }),
};
