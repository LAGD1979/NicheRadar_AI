import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../api";
import {
  LANGUAGES,
  MAX_SEARCH_CALLS_LIMIT,
  WINDOWS,
  buildDiscoveryRequest,
  estimatedUnits,
  type DiscoveryForm,
} from "../discovery";
import { formatDateTime, formatNumber, label } from "../format";
import type { RunOut } from "../types";

const INITIAL_FORM: DiscoveryForm = {
  language: "es",
  query: "",
  window: "8-30",
  maxSearchCalls: 1,
};

export function Runs() {
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 5000 });
  const [form, setForm] = useState<DiscoveryForm>(INITIAL_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["runs"] });
    void queryClient.invalidateQueries({ queryKey: ["usage"] });
  };
  const demo = useMutation({ mutationFn: api.createDemoRun, onSuccess: refresh });
  const discovery = useMutation({ mutationFn: api.createRun, onSuccess: refresh });
  const resume = useMutation({ mutationFn: api.resumeRun, onSuccess: refresh });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = buildDiscoveryRequest(form);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setFormError(null);
    discovery.mutate(result.body);
  }

  return (
    <section aria-labelledby="titulo-corridas">
      <h1 id="titulo-corridas">Corridas</h1>
      <p className="hint">
        Una búsqueda en YouTube consume cuota oficial (cada búsqueda cuesta {formatNumber(estimatedUnits(1))} unidades).
        La corrida DEMO no consulta nada externo.
      </p>

      <form className="filters" onSubmit={submit} aria-label="Nueva búsqueda en YouTube">
        <label>
          Idioma
          <select value={form.language} onChange={(e) => { setForm({ ...form, language: e.target.value }); }}>
            {LANGUAGES.map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <label>
          Consulta
          <input
            type="text"
            required
            minLength={2}
            maxLength={200}
            value={form.query}
            onChange={(e) => { setForm({ ...form, query: e.target.value }); }}
            placeholder="p. ej. historia con mapas"
          />
        </label>
        <label>
          Ventana
          <select value={form.window} onChange={(e) => { setForm({ ...form, window: e.target.value }); }}>
            {WINDOWS.map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <label>
          Búsquedas máx.
          <input
            type="number"
            min={1}
            max={MAX_SEARCH_CALLS_LIMIT}
            value={form.maxSearchCalls}
            onChange={(e) => { setForm({ ...form, maxSearchCalls: Number(e.target.value) }); }}
          />
        </label>
        <button type="submit" disabled={discovery.isPending}>
          {discovery.isPending ? "Encolando…" : "Buscar en YouTube"}
        </button>
      </form>
      <p className="muted">
        Costo máximo estimado: {formatNumber(estimatedUnits(form.maxSearchCalls))} unidades (sin contar detalles de video).
      </p>
      <div className="toolbar">
        <button type="button" onClick={() => { demo.mutate(); }} disabled={demo.isPending}>
          Iniciar corrida DEMO
        </button>
      </div>
      {formError && <p role="alert">{formError}</p>}
      {discovery.isSuccess && <p role="status">Búsqueda encolada. El worker la ejecuta en segundo plano.</p>}
      {discovery.isError && <ErrorNote error={discovery.error} prefix="No se pudo iniciar la búsqueda" />}
      {demo.isSuccess && <p role="status">Corrida DEMO encolada.</p>}
      {resume.isError && <ErrorNote error={resume.error} prefix="No se pudo reanudar" />}

      {runs.isPending && <p>Cargando corridas…</p>}
      {runs.isError && <p role="alert">No se pudieron cargar las corridas: {runs.error.message}.</p>}
      {runs.isSuccess && runs.data.items.length === 0 && <p className="empty">Aún no hay corridas.</p>}
      {runs.isSuccess && runs.data.items.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Corrida</th>
                <th scope="col">Tipo</th>
                <th scope="col">Estado</th>
                <th scope="col">Inicio</th>
                <th scope="col">Resultado</th>
                <th scope="col">Incidencias</th>
                <th scope="col">Acción</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.items.map((run) => (
                <RunRow key={run.id} run={run} onResume={() => { resume.mutate(run.id); }} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RunRow({ run, onResume }: { run: RunOut; onResume: () => void }) {
  const queries = run.coverage.queries_completed;
  const total = run.coverage.queries_total;
  const channelCount = run.coverage.channels;
  let result = "Sin dato";
  if (typeof queries === "number" && typeof total === "number") {
    result = `${String(queries)} de ${String(total)} consultas`;
  } else if (typeof channelCount === "number") {
    result = `${String(channelCount)} canales sintéticos`;
  }
  return (
    <tr>
      <td>
        <code>{run.id.slice(0, 8)}</code>
      </td>
      <td>{label(run.kind)}</td>
      <td>{label(run.status)}</td>
      <td>{formatDateTime(run.started_at)}</td>
      <td>{result}</td>
      <td>
        {run.errors.length === 0
          ? "Ninguna"
          : run.errors.map((e) => `${String(e.code)}: ${detailText(e.detail)}`).join(" · ")}
      </td>
      <td>
        {run.status === "PAUSED_QUOTA" && (
          <button type="button" onClick={onResume}>
            Reanudar
          </button>
        )}
      </td>
    </tr>
  );
}

function detailText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function ErrorNote({ error, prefix }: { error: Error; prefix: string }) {
  return (
    <p role="alert">
      {prefix}: {error.message}.
    </p>
  );
}
