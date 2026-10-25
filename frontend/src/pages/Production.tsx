import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { formatField, formatNumber, label, stateFor } from "../format";
import type { EvaluationOut } from "../types";

const FACELESS = [
  ["FACELESS_CONFIRMED", "Confirmado"],
  ["FACELESS_LIKELY", "Probable"],
  ["MIXED", "Mixto"],
  ["NOT_FACELESS", "No faceless"],
  ["UNKNOWN", "Desconocido"],
];
const RIGHTS = [
  ["LOW", "Bajo"],
  ["MEDIUM", "Medio"],
  ["HIGH", "Alto"],
  ["UNKNOWN", "Desconocido"],
];
const SCENARIOS = ["low", "base", "high"] as const;
type Scenario = (typeof SCENARIOS)[number];
const SCENARIO_LABEL: Record<Scenario, string> = { low: "Bajo", base: "Base", high: "Alto" };

interface LineForm {
  name: string;
  unit: string;
  quantity: string;
  prices: Record<Scenario, string>;
}

const DEFAULT_LINES: LineForm[] = [
  { name: "Narración (TTS)", unit: "1000 caracteres", quantity: "", prices: { low: "", base: "", high: "" } },
  { name: "Ilustraciones o imágenes", unit: "imagen", quantity: "", prices: { low: "", base: "", high: "" } },
  { name: "Música licenciada", unit: "pista", quantity: "", prices: { low: "", base: "", high: "" } },
  { name: "Edición y revisión humana", unit: "hora", quantity: "", prices: { low: "", base: "", high: "" } },
];

function textOr(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function toNumberOrNull(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}

export function ProductionPanel({ opportunityId, evaluation }: { opportunityId: string; evaluation: EvaluationOut | null }) {
  const queryClient = useQueryClient();
  const cost = useQuery({
    queryKey: ["cost-model", opportunityId],
    queryFn: () => api.costModel(opportunityId),
    retry: false,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["cost-model", opportunityId] });
    void queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
  };

  const feas = evaluation?.feasibility ?? {};
  const [faceless, setFaceless] = useState(textOr(feas.faceless_state, "UNKNOWN"));
  const [rights, setRights] = useState(textOr(feas.rights_risk, "UNKNOWN"));
  const [complexity, setComplexity] = useState("");
  const [minutes, setMinutes] = useState("");
  const [coverage, setCoverage] = useState("");
  const [facelessReason, setFacelessReason] = useState("");
  const [rightsNotes, setRightsNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const saveFeasibility = useMutation({ mutationFn: (body: unknown) => api.saveFeasibility(opportunityId, body), onSuccess: refresh });

  function submitFeasibility(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (facelessReason.trim().length < 20) {
      setFormError("Explique en al menos 20 caracteres por qué el formato es o no es faceless.");
      return;
    }
    setFormError(null);
    saveFeasibility.mutate({
      faceless_state: faceless,
      complexity_1_to_5: complexity === "" ? null : Number(complexity),
      rights_risk: rights,
      rights_notes: rightsNotes || null,
      faceless_reason: facelessReason,
      human_review_required: true,
      human_minutes_per_video: toNumberOrNull(minutes),
      ai_pipeline_coverage_pct: toNumberOrNull(coverage),
    });
  }

  const [duration, setDuration] = useState("10");
  const [wpm, setWpm] = useState("150");
  const [lines, setLines] = useState<LineForm[]>(DEFAULT_LINES);
  const saveCost = useMutation({ mutationFn: (body: unknown) => api.saveCostModel(opportunityId, body), onSuccess: refresh });

  function submitCost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveCost.mutate({
      duration_minutes: Number(duration),
      words_per_minute: Number(wpm),
      lines: lines.map((l) => ({
        name: l.name,
        unit: l.unit,
        quantity: Number(l.quantity || 0),
        prices: { low: toNumberOrNull(l.prices.low), base: toNumberOrNull(l.prices.base), high: toNumberOrNull(l.prices.high) },
      })),
    });
  }

  function updateLine(index: number, patch: Partial<LineForm>) {
    setLines(lines.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  const totals = cost.data?.scenarios.usd_per_video;
  return (
    <div>
      <h3>Costo estimado por video (USD)</h3>
      <p className="hint">
        Los precios los escribe una persona. Un precio vacío deja el total en «Sin dato»; nunca se convierte en 0.
      </p>
      {cost.isSuccess && totals && (
        <dl className="facts">
          {SCENARIOS.map((s) => (
            <div key={s}>
              <dt>{SCENARIO_LABEL[s]}</dt>
              <dd>{formatField(totals[s] ?? null, stateFor(totals[s]))}</dd>
            </div>
          ))}
          {SCENARIOS.some((s) => (cost.data.missing[s] ?? []).length > 0) && (
            <>
              <dt>Falta precio de</dt>
              <dd>{SCENARIOS.map((s) => (cost.data.missing[s] ?? []).join(", ")).filter(Boolean).join(" · ")}</dd>
            </>
          )}
        </dl>
      )}
      {cost.isError && <p className="muted">Aún no hay modelo de costo para esta oportunidad.</p>}

      <form onSubmit={submitCost} aria-label="Modelo de costo">
        <div className="filters">
          <label>
            Duración (min)
            <input type="number" min={0.5} max={60} step={0.5} value={duration} onChange={(e) => { setDuration(e.target.value); }} />
          </label>
          <label>
            Palabras por minuto
            <input type="number" min={60} max={220} value={wpm} onChange={(e) => { setWpm(e.target.value); }} />
          </label>
          <p className="muted">Palabras del guion: {formatNumber(Math.round(Number(duration) * Number(wpm)) || 0)}</p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Concepto</th>
                <th scope="col">Unidad</th>
                <th scope="col">Cantidad</th>
                {SCENARIOS.map((s) => (
                  <th scope="col" key={s}>Precio {SCENARIO_LABEL[s].toLowerCase()}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.map((line, index) => (
                <tr key={line.name}>
                  <td>{line.name}</td>
                  <td>{line.unit}</td>
                  <td>
                    <input aria-label={`Cantidad de ${line.name}`} type="number" min={0} value={line.quantity} onChange={(e) => { updateLine(index, { quantity: e.target.value }); }} />
                  </td>
                  {SCENARIOS.map((s) => (
                    <td key={s}>
                      <input
                        aria-label={`Precio ${SCENARIO_LABEL[s]} de ${line.name}`}
                        type="number"
                        min={0}
                        step="0.0001"
                        placeholder="sin dato"
                        value={line.prices[s]}
                        onChange={(e) => { updateLine(index, { prices: { ...line.prices, [s]: e.target.value } }); }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button type="submit" disabled={saveCost.isPending}>Guardar modelo de costo</button>
        {saveCost.isError && <p role="alert">{saveCost.error instanceof ApiError ? saveCost.error.message : "No se pudo guardar."}</p>}
      </form>

      <h3>Factibilidad (valoración humana)</h3>
      <p className="hint">
        La factibilidad no se deduce de una miniatura ni de un título. Una persona la valora y deja el motivo.
      </p>
      <form onSubmit={submitFeasibility} aria-label="Factibilidad" className="filters">
        <label>
          Faceless
          <select value={faceless} onChange={(e) => { setFaceless(e.target.value); }}>
            {FACELESS.map(([v, t]) => (
              <option key={v} value={v}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Riesgo de derechos
          <select value={rights} onChange={(e) => { setRights(e.target.value); }}>
            {RIGHTS.map(([v, t]) => (
              <option key={v} value={v}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Complejidad (1–5)
          <input type="number" min={1} max={5} value={complexity} onChange={(e) => { setComplexity(e.target.value); }} />
        </label>
        <label>
          Minutos humanos por video
          <input type="number" min={0} value={minutes} onChange={(e) => { setMinutes(e.target.value); }} />
        </label>
        <label>
          % del proceso con IA
          <input type="number" min={0} max={100} value={coverage} onChange={(e) => { setCoverage(e.target.value); }} />
        </label>
        <label>
          Motivo del faceless (obligatorio)
          <textarea rows={3} value={facelessReason} onChange={(e) => { setFacelessReason(e.target.value); }} />
        </label>
        <label>
          Notas de derechos (obligatorias si el riesgo es medio o alto)
          <textarea rows={3} value={rightsNotes} onChange={(e) => { setRightsNotes(e.target.value); }} />
        </label>
        <button type="submit" disabled={saveFeasibility.isPending}>Guardar valoración</button>
      </form>
      {formError && <p role="alert">{formError}</p>}
      {saveFeasibility.isError && <p role="alert">{saveFeasibility.error.message}</p>}
      {saveFeasibility.isSuccess && (
        <p role="status">
          Valoración guardada (versión {saveFeasibility.data.evaluation_version}). Recomendación:{" "}
          {label(saveFeasibility.data.recommendation)}.
        </p>
      )}
    </div>
  );
}
