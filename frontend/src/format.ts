import type { FieldState } from "./types";

// Etiquetas en español para los códigos de estado. Un código desconocido se muestra tal cual.
const LABELS: Record<string, string> = {
  LOW: "Baja",
  MEDIUM: "Media",
  HIGH: "Alta",
  UNKNOWN: "Desconocida",
  OBSERVED: "Observada",
  INDICATIVE: "Indicativa",
  UNPROVEN: "No demostrada",
  NOT_OBSERVED: "No observada",
  GAP_CONFIRMED: "Brecha confirmada",
  POTENTIAL_GAP: "Posible brecha",
  CROWDED: "Saturada",
  DEMAND_UNPROVEN: "Demanda no demostrada",
  INSUFFICIENT_EVIDENCE: "Evidencia insuficiente",
  REPLICATED: "Replicado",
  PROMISING: "Prometedor",
  SINGLE_OUTLIER: "Caso aislado",
  FACELESS_CONFIRMED: "Faceless confirmado",
  FACELESS_LIKELY: "Faceless probable",
  MIXED: "Mixto",
  NOT_FACELESS: "No faceless",
  LONG: "Largo",
  SHORT: "Short",
  LIVE: "En vivo",
  CONFLICT: "Conflicto",
  VALIDATE_DEMAND_PILOT: "Validar demanda con piloto",
  READY_FOR_PILOT: "Listo para piloto",
  HIGH_COPYRIGHT_RISK: "Riesgo alto de derechos",
  RIGHTS_NOT_ASSESSED: "Derechos sin evaluar",
  FACELESS_NOT_ASSESSED: "Faceless sin evaluar",
  COMPLEXITY_NOT_ASSESSED: "Complejidad sin evaluar",
  MORE_RESEARCH: "Investigar más",
  WATCHLIST: "Vigilar",
  REJECT: "Descartar",
  SCREENED: "Descubierta",
  ES_UNCHECKED: "ES sin verificar",
  ES_VALIDATION_IN_PROGRESS: "Validación ES en curso",
  ES_COMPETITIVE: "Competitiva en ES",
  ES_DEMAND_UNPROVEN: "Demanda ES no demostrada",
  FEASIBILITY_PENDING: "Factibilidad pendiente",
  COMPLETED: "Completada",
  PARTIAL: "Parcial",
  PAUSED_QUOTA: "Pausada por cuota",
  OFFICIAL: "YouTube oficial",
  PROVIDER: "Proveedor importado",
  HUMAN: "Revisión humana",
  AI_INFERENCE: "Inferencia IA",
  discovery: "Búsqueda en YouTube",
  demand: "Medición de demanda",
  history: "Persistencia de videos",
  PRESENT: "Presente",
  NOT_PRESENT: "No alcanza",
  google_trends: "Google Trends (HasData)",
  vidiq_keywords: "Palabras clave (vidIQ)",
  youtube_consumption: "Consumo de competidores",
  hasdata: "HasData",
  vidiq: "Consulta a vidIQ",
  vidiq_api: "vidIQ",
  youtube_official: "YouTube oficial",
  demo: "Corrida DEMO",
  purge: "Purga de caducados",
  backup: "Backup de la base",
  OK: "Correcta",
  ERROR: "Con error",
  QUEUED: "En cola",
  RUNNING: "En ejecución",
  FAILED: "Fallida",
  PENDING: "Pendiente",
  SYNTHETIC: "Sintético",
  SIN_EVALUACION: "Sin evaluación",
  AVAILABLE: "Disponible",
  EXPIRED: "Caducada",
  RESTRICTED: "Restringido",
  NOT_CONFIGURED: "No configurado",
  CONFIGURED: "Configurado",
  DISABLED: "Desactivado",
  STRONG: "Fuerte",
  WEAK: "Débil",
  CONFIRMED: "Confirmado",
  HIGH_RISK: "Riesgo alto",
  MEDIUM_RISK: "Riesgo medio",
};

export const NO_DATA = "Sin dato";
export const NOT_ENABLED = "No habilitado";

export function label(code: string | null | undefined): string {
  if (code === null || code === undefined || code === "") return NO_DATA;
  return LABELS[code] ?? code;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("es-CL", { maximumFractionDigits: 1 })} ${units[unit] ?? "GB"}`;
}

export function formatNumber(value: number): string {
  return value.toLocaleString("es-CL", { maximumFractionDigits: 2 });
}

export function formatUsd(value: number): string {
  return `USD ${value.toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Un valor NULL nunca se muestra como 0; los restringidos muestran "No habilitado".
export function formatField(value: unknown, state: FieldState): string {
  if (state === "RESTRICTED") return NOT_ENABLED;
  if (value === null || value === undefined || value === "") return NO_DATA;
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (typeof value === "string") return label(value);
  return NO_DATA;
}

export function stateFor(value: unknown): FieldState {
  return value === null || value === undefined ? "NOT_AVAILABLE" : "AVAILABLE";
}

export function cell(value: string | null | undefined): string {
  return formatField(value ?? null, stateFor(value ?? null));
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return NO_DATA;
  return new Date(iso).toLocaleString("es-CL", {
    timeZone: "America/Santiago",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatAgeHours(hours: number | null): string {
  if (hours === null) return NO_DATA;
  if (hours < 48) return `${formatNumber(Math.round(hours))} h`;
  return `${formatNumber(Math.round(hours / 24))} días`;
}

// Días que quedan antes de que caduque un dato de terceros (29 días desde que se observó).
export function daysLeft(deadline: string | null, now: number = Date.now()): number | null {
  if (!deadline) return null;
  return Math.ceil((new Date(deadline).getTime() - now) / 86_400_000);
}
