// Formulario de búsqueda en YouTube (M1). La validación refleja la de la API (backend/app/api/v1/schemas.py).

export const LANGUAGES: Array<[string, string]> = [
  ["es", "Español"],
  ["en", "Inglés"],
  ["pt", "Portugués"],
  ["fr", "Francés"],
  ["de", "Alemán"],
  ["it", "Italiano"],
  ["ar", "Árabe"],
  ["hi", "Hindi"],
  ["ja", "Japonés"],
  ["ko", "Coreano"],
  ["tr", "Turco"],
  ["ru", "Ruso"],
  ["id", "Indonesio"],
  ["vi", "Vietnamita"],
  ["zh-Hans", "Chino simplificado"],
  ["zh-Hant", "Chino tradicional"],
];

export const WINDOWS: Array<[string, string]> = [
  ["0-7", "0 a 7 días"],
  ["8-30", "8 a 30 días"],
  ["31-90", "31 a 90 días"],
];

export const MAX_SEARCH_CALLS_LIMIT = 80;
// search.list cuesta 100 unidades de cuota (ver docs/DECISIONS.md, D-22).
export const UNITS_PER_SEARCH = 100;

export interface DiscoveryForm {
  language: string;
  query: string;
  window: string;
  maxSearchCalls: number;
}

export interface DiscoveryBody {
  kind: "discovery";
  payload: {
    queries: Array<{ language: string; query: string; window: string }>;
    max_search_calls: number;
    pages_per_query: number;
  };
}

export type DiscoveryResult = { ok: true; body: DiscoveryBody } | { ok: false; error: string };

export function buildDiscoveryRequest(form: DiscoveryForm): DiscoveryResult {
  const query = form.query.trim();
  if (query.length < 2 || query.length > 200) {
    return { ok: false, error: "La consulta debe tener entre 2 y 200 caracteres." };
  }
  if (!Number.isInteger(form.maxSearchCalls) || form.maxSearchCalls < 1 || form.maxSearchCalls > MAX_SEARCH_CALLS_LIMIT) {
    return { ok: false, error: `Las búsquedas deben estar entre 1 y ${String(MAX_SEARCH_CALLS_LIMIT)}.` };
  }
  return {
    ok: true,
    body: {
      kind: "discovery",
      payload: {
        queries: [{ language: form.language, query, window: form.window }],
        max_search_calls: form.maxSearchCalls,
        pages_per_query: 1,
      },
    },
  };
}

// Unidades estimadas antes de enviar: el usuario ve el costo antes de gastar cuota.
export function estimatedUnits(maxSearchCalls: number): number {
  return maxSearchCalls * UNITS_PER_SEARCH;
}
