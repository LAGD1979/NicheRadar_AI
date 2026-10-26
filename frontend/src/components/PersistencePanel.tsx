import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../api";
import { formatNumber, label } from "../format";
import type { OpportunityDetail } from "../types";

const VIDIQ_CREDITS = 5;

const STATE_TEXT: Record<string, string> = {
  NO_VIDEOS: "Aún no hay videos agrupados con confianza alta o media.",
  INSUFFICIENT_VIDEOS: "Pocos videos con historial suficiente para puntuar (se necesitan 3).",
};

function count(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

// Persistencia de la velocidad: segunda semana contra la primera desde la publicación.
export function PersistencePanel({ opp }: { opp: OpportunityDetail }) {
  const queryClient = useQueryClient();
  const relevant = opp.evidence.filter((e) => e.market === "SOURCE_MARKET").length;
  const [calls, setCalls] = useState(Math.min(10, Math.max(1, relevant || 3)));
  const summary = (opp.evaluation?.international.temporal_resilience ?? null) as Record<string, unknown> | null;
  const ratio = typeof summary?.ratio === "number" ? summary.ratio : null;
  const state = typeof summary?.state === "string" ? summary.state : null;

  const run = useMutation({
    mutationFn: () => api.requestHistory(opp.id, calls),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["vidiq-usage"] });
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["opportunity", opp.id] });
      }, 20000);
    },
  });

  return (
    <section aria-labelledby="persistencia-titulo" className="persistence">
      <h3 id="persistencia-titulo">
        Persistencia de la velocidad:{" "}
        <strong>{ratio === null ? "Sin dato" : `${formatNumber(ratio)} de 1`}</strong>
      </h3>
      <p className="hint">
        Compara las vistas por día de la segunda semana con las de la primera, desde la publicación. 1 significa que
        el video mantuvo su ritmo; cerca de 0, que se apagó. Es la mediana de los videos con historial suficiente.
      </p>
      {summary && (
        <p className="muted">
          Videos medidos: {formatNumber(count(summary.videos_evaluated))} · sin historial suficiente:{" "}
          {formatNumber(count(summary.videos_without_enough_history))}
          {state && state !== "OBSERVED" && <> · {STATE_TEXT[state] ?? label(state)}</>}
        </p>
      )}
      <div className="toolbar">
        <label>
          Videos a medir (máx.)
          <input
            type="number"
            min={1}
            max={10}
            value={calls}
            onChange={(e) => { setCalls(Number(e.target.value)); }}
          />
        </label>
        <button type="button" onClick={() => { run.mutate(); }} disabled={run.isPending || calls < 1 || calls > 10}>
          {run.isPending ? "Encolando…" : "Medir persistencia (vidIQ)"}
        </button>
        <span className="muted small">Hasta {formatNumber(calls * VIDIQ_CREDITS)} créditos de vidIQ.</span>
      </div>
      {run.isError && (
        <p role="alert">{run.error instanceof ApiError ? run.error.message : "No se pudo iniciar la medición."}</p>
      )}
      {run.isSuccess && <p role="status">Medición encolada. Recargue la ficha en unos segundos para ver el resultado.</p>}
    </section>
  );
}
