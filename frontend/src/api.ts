import type {
  CapabilityOut,
  CompareResponse,
  ConfigPublic,
  OpportunityDetail,
  OpportunityItem,
  Page,
  ProblemBody,
  ProviderOut,
  RunOut,
  UsageOut,
  VideoItem,
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
};
