import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CompetitionPanel } from "../components/CompetitionPanel";
import { DemandPanel } from "../components/DemandPanel";
import { api } from "../api";
import { label } from "../format";
import type { SearchPlan, SearchPlanBody } from "../types";

const WINDOW_OPTIONS: Array<[string, string]> = [
  ["0-7", "0 a 7 días"],
  ["8-30", "8 a 30 días"],
  ["31-90", "31 a 90 días"],
];
const PLAN_TEMPLATE: SearchPlanBody = {
  schema_version: "1.0",
  canonical_concept_es: "Escriba el concepto en español",
  same_format_definition: "Describa qué narrativa y estética deben coincidir.",
  query_groups: [
    {
      region: "ALL_ES",
      language: "es",
      queries: ["búsqueda 1", "búsqueda 2", "búsqueda 3", "búsqueda 4", "búsqueda 5"],
      exclusions: [],
    },
  ],
  adjacent_but_distinct: [],
  localization_notes: [],
  source_ids: [],
};

const STATUS_LABEL: Record<string, string> = {
  PENDING_REVIEW: "Pendiente de revisión",
  APPROVED: "Aprobado",
  NEEDS_REVIEW: "Requiere revisión",
  SUPERSEDED: "Reemplazado",
};

export function SpanishMarket({ opportunityId, smallAccess }: { opportunityId: string; smallAccess?: unknown }) {
  const queryClient = useQueryClient();
  const plans = useQuery({
    queryKey: ["plans", opportunityId],
    queryFn: () => api.plans(opportunityId),
    refetchInterval: 5000,
  });
  const competition = useQuery({
    queryKey: ["competition", opportunityId],
    queryFn: () => api.competition(opportunityId),
    refetchInterval: 5000,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["plans", opportunityId] });
    void queryClient.invalidateQueries({ queryKey: ["competition", opportunityId] });
    void queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
  };

  const generate = useMutation({ mutationFn: () => api.generatePlan(opportunityId), onSuccess: refresh });
  const createManual = useMutation({
    mutationFn: (body: unknown) => api.createManualPlan(opportunityId, body),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: (plan: SearchPlan) =>
      api.updatePlan(plan.id, { plan: plan.plan, approve: true }),
    onSuccess: refresh,
  });

  const approved = plans.data?.find((p) => p.status === "APPROVED");
  const [manualText, setManualText] = useState(JSON.stringify(PLAN_TEMPLATE, null, 2));
  const [manualError, setManualError] = useState<string | null>(null);
  const [windows, setWindows] = useState<string[]>(["8-30", "31-90"]);
  const [maxSearches, setMaxSearches] = useState(5);
  const validate = useMutation({
    mutationFn: () =>
      api.validateSpanish(opportunityId, {
        plan_id: approved?.id ?? "",
        windows,
        max_search_calls: maxSearches,
        pages_per_query: 1,
      }),
    onSuccess: refresh,
  });

  function submitManual() {
    try {
      createManual.mutate(JSON.parse(manualText) as unknown);
      setManualError(null);
    } catch {
      setManualError("El texto no es JSON válido.");
    }
  }

  return (
    <div>
      <p className="hint">
        Una búsqueda sin resultados no prueba oportunidad ni baja competencia. El estado solo cambia con
        evidencia revisada.
      </p>

      {competition.data && (
        <p>
          Consultas ejecutadas: <strong>{competition.data.coverage.queries_run}</strong> · Videos en español verificados:{" "}
          <strong>{competition.data.coverage.es_verified_videos}</strong> · Revisados:{" "}
          <strong>{competition.data.coverage.reviewed_matches}</strong> · Competidores exactos:{" "}
          <strong>{competition.data.coverage.exact_matches}</strong>
        </p>
      )}
      <SmallAccess value={smallAccess} />
      <DemandPanel opportunityId={opportunityId} />

      <h3>Planes de búsqueda</h3>
      <div className="toolbar">
        <button type="button" onClick={() => { generate.mutate(); }} disabled={generate.isPending}>
          Generar plan con IA
        </button>
      </div>
      {generate.isError && <p role="alert">No se pudo generar: {generate.error.message}.</p>}
      {generate.isSuccess && <p role="status">Plan encolado. Aparecerá aquí cuando el worker termine.</p>}

      {plans.isSuccess && plans.data.length === 0 && <p className="empty">Aún no hay planes para esta oportunidad.</p>}
      <ul className="list">
        {plans.data?.map((plan) => (
          <li key={plan.id}>
            <strong>{plan.plan.canonical_concept_es ?? "Plan sin contenido válido"}</strong>{" "}
            <span className="muted">
              · {STATUS_LABEL[plan.status] ?? plan.status} · Origen: {label(plan.origin)}
              {plan.error_code && ` · Error: ${plan.error_code}`}
            </span>
            {plan.plan.query_groups && (
              <ul>
                {plan.plan.query_groups.flatMap((g) =>
                  g.queries.map((q) => (
                    <li key={`${g.region}-${q}`}>
                      {q} <small className="muted">({g.region})</small>
                    </li>
                  )),
                )}
              </ul>
            )}
            {plan.status === "PENDING_REVIEW" && (
              <button type="button" onClick={() => { approve.mutate(plan); }} disabled={approve.isPending}>
                Aprobar este plan
              </button>
            )}
          </li>
        ))}
      </ul>
      {approve.isError && <p role="alert">No se pudo aprobar: {approve.error.message}.</p>}

      <details>
        <summary>Escribir un plan manualmente (JSON)</summary>
        <textarea
          aria-label="Plan en JSON"
          rows={14}
          value={manualText}
          onChange={(e) => { setManualText(e.target.value); }}
          style={{ width: "100%", fontFamily: "monospace" }}
        />
        <button type="button" onClick={submitManual} disabled={createManual.isPending}>
          Guardar plan
        </button>
        {manualError && <p role="alert">{manualError}</p>}
        {createManual.isError && <p role="alert">{createManual.error.message}</p>}
      </details>

      <h3>Validar en español</h3>
      {approved ? (
        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault();
            validate.mutate();
          }}
          aria-label="Validar en español"
        >
          <fieldset>
            <legend>Ventanas</legend>
            {WINDOW_OPTIONS.map(([code, text]) => (
              <label key={code}>
                <input
                  type="checkbox"
                  checked={windows.includes(code)}
                  onChange={(e) => {
                    setWindows(e.target.checked ? [...windows, code] : windows.filter((w) => w !== code));
                  }}
                />{" "}
                {text}
              </label>
            ))}
          </fieldset>
          <label>
            Búsquedas máx.
            <input
              type="number"
              min={1}
              max={80}
              value={maxSearches}
              onChange={(e) => { setMaxSearches(Number(e.target.value)); }}
            />
          </label>
          <button type="submit" disabled={validate.isPending || windows.length === 0}>
            Validar en español
          </button>
        </form>
      ) : (
        <p className="empty">Apruebe un plan para poder validarlo en español.</p>
      )}
      {validate.isSuccess && <p role="status">Validación encolada.</p>}
      {validate.isError && <p role="alert">No se pudo validar: {validate.error.message}.</p>}

      <CompetitionPanel opportunityId={opportunityId} />
    </div>
  );
}

const SMALL_ACCESS_STATES: Record<string, string> = {
  NO_EXACT_MATCHES: "Sin competidores exactos revisados: todavía no se puede medir.",
  INSUFFICIENT_SAMPLE: "Muestra insuficiente: faltan competidores exactos con vistas y suscriptores.",
};

// Éxito accesible a canales pequeños: evidencia observada, no un censo de competidores.
function SmallAccess({ value }: { value: unknown }) {
  if (typeof value !== "object" || value === null) return null;
  const access = value as Record<string, unknown>;
  const state = typeof access.state === "string" ? access.state : "";
  const ratio = typeof access.ratio === "number" ? access.ratio : null;
  return (
    <p>
      Éxito accesible a canales pequeños:{" "}
      <strong>{ratio === null ? "Sin dato" : `${String(Math.round(ratio * 100))} %`}</strong>
      {ratio === null && SMALL_ACCESS_STATES[state] ? ` · ${SMALL_ACCESS_STATES[state]}` : ""}
      {ratio !== null && (
        <>
          {" "}
          de los competidores exactos observados ({String(access.small_channel_successes)} de {String(access.evaluated)})
          son canales pequeños con vistas altas.
        </>
      )}
    </p>
  );
}
