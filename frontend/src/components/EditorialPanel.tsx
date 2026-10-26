import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import type { EvaluationOut } from "../types";

const DIFFERENTIATION: Array<[string, string]> = [
  ["HIGH", "Alta: ángulo propio claro"],
  ["MEDIUM", "Media: algo distinto de lo que existe"],
  ["LOW", "Baja: se parece a lo que ya hay"],
];
const MAINTENANCE: Array<[string, string]> = [
  ["LOW_EFFORT", "Poco esfuerzo: contenido estable"],
  ["MODERATE", "Moderado: revisar cifras cada cierto tiempo"],
  ["HIGH_EFFORT", "Mucho esfuerzo: datos que cambian seguido"],
];
const MIN_REASON = 20;

interface Level {
  level?: string;
  reason?: string;
}

function levelOf(value: unknown): Level {
  return typeof value === "object" && value !== null ? (value as Level) : {};
}

// Dos juicios humanos que alimentan el índice: diferenciación editorial y mantenibilidad.
export function EditorialPanel({ opportunityId, evaluation }: { opportunityId: string; evaluation: EvaluationOut | null }) {
  const queryClient = useQueryClient();
  const saved = (evaluation?.feasibility.editorial ?? {}) as Record<string, unknown>;
  const savedDiff = levelOf(saved.differentiation);
  const savedMaint = levelOf(saved.maintainability);
  const [diff, setDiff] = useState(savedDiff.level ?? "");
  const [diffReason, setDiffReason] = useState(savedDiff.reason ?? "");
  const [maint, setMaint] = useState(savedMaint.level ?? "");
  const [maintReason, setMaintReason] = useState(savedMaint.reason ?? "");
  const [formError, setFormError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      api.saveEditorial(opportunityId, {
        differentiation: diff,
        differentiation_reason: diffReason.trim(),
        maintainability: maint,
        maintainability_reason: maintReason.trim(),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
    },
  });

  function problem(): string | null {
    if (!diff || !maint) return "Elija un nivel de diferenciación y uno de mantenibilidad.";
    if (diffReason.trim().length < MIN_REASON || maintReason.trim().length < MIN_REASON) {
      return `Cada valoración necesita un motivo de ${String(MIN_REASON)} caracteres o más.`;
    }
    return null;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = problem();
    setFormError(found);
    if (found === null) save.mutate();
  }

  return (
    <section aria-labelledby="editorial-titulo">
      <h3 id="editorial-titulo">Valoración editorial (valoración humana)</h3>
      <p className="hint">
        Alimenta dos dimensiones del índice: qué tan distinta es su propuesta y cuánto cuesta mantenerla al día. Sin
        valoración, esas dimensiones quedan sin dato; la herramienta no las supone.
      </p>
      <form onSubmit={submit} aria-label="Valoración editorial" className="filters">
        <label>
          Diferenciación
          <select value={diff} onChange={(e) => { setDiff(e.target.value); }}>
            <option value="">Elija…</option>
            {DIFFERENTIATION.map(([v, t]) => (
              <option key={v} value={v}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          Motivo de la diferenciación
          <textarea rows={3} value={diffReason} onChange={(e) => { setDiffReason(e.target.value); }} />
        </label>
        <label>
          Mantenibilidad
          <select value={maint} onChange={(e) => { setMaint(e.target.value); }}>
            <option value="">Elija…</option>
            {MAINTENANCE.map(([v, t]) => (
              <option key={v} value={v}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          Motivo de la mantenibilidad
          <textarea rows={3} value={maintReason} onChange={(e) => { setMaintReason(e.target.value); }} />
        </label>
        <button type="submit" disabled={save.isPending}>
          Guardar valoración editorial
        </button>
      </form>
      {formError && <p role="alert">{formError}</p>}
      {save.isError && (
        <p role="alert">{save.error instanceof ApiError ? save.error.message : "No se pudo guardar."}</p>
      )}
      {save.isSuccess && <p role="status">Valoración editorial guardada (versión {save.data.evaluation_version}).</p>}
    </section>
  );
}
