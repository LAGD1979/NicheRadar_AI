import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { ExplorationSteps } from "../components/ExplorationSteps";
import { VidiqCard } from "../components/VidiqCard";
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
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
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
      <ExplorationSteps current="discover" />
      <h1 id="titulo-corridas">Corridas</h1>
      <p className="hint">
        Aquí empieza la exploración: elija una fuente para traer videos. Después los verá en{" "}
        <Link to="/videos">Videos</Link>, donde se agrupan en oportunidades.
      </p>

      <div className="source-grid">
        <VidiqCard />

        <article className="source-card" aria-labelledby="youtube-titulo">
          <header className="source-head">
            <div>
              <h2 id="youtube-titulo">YouTube · búsqueda por consulta</h2>
              <p className="muted">
                Búsqueda oficial por idioma y ventana. Cada búsqueda cuesta {formatNumber(estimatedUnits(1))} unidades de
                cuota.
              </p>
            </div>
          </header>
          <form className="source-form" onSubmit={submit} aria-label="Nueva búsqueda en YouTube">
            <div className="fields">
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
              <label className="wide">
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
            </div>
            <footer className="source-foot">
              <p className="muted">
                Costo máximo estimado: {formatNumber(estimatedUnits(form.maxSearchCalls))} unidades (sin contar
                detalles de video).
              </p>
              <button type="submit" disabled={discovery.isPending}>
                {discovery.isPending ? "Encolando…" : "Buscar en YouTube"}
              </button>
            </footer>
          </form>
          {formError && <p role="alert">{formError}</p>}
          {discovery.isSuccess && <p role="status">Búsqueda encolada. El worker la ejecuta en segundo plano.</p>}
          {discovery.isError && <ErrorNote error={discovery.error} prefix="No se pudo iniciar la búsqueda" />}
        </article>
      </div>

      <div className="toolbar">
        <h2 className="section-title">Historial de corridas</h2>
        {config.data?.demo_mode !== false && (
          <button type="button" className="ghost" onClick={() => { demo.mutate(); }} disabled={demo.isPending}>
            Iniciar corrida DEMO
          </button>
        )}
      </div>
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

function resultText(run: RunOut): string {
  const queries = run.coverage.queries_completed;
  const total = run.coverage.queries_total;
  const channelCount = run.coverage.channels;
  if (run.kind === "vidiq") {
    const fresh = run.coverage.videos_new;
    const credits = run.coverage.credits;
    if (typeof fresh === "number" && typeof credits === "number") {
      return `${String(fresh)} videos nuevos · ${String(credits)} créditos`;
    }
    return "Sin dato";
  }
  if (typeof queries === "number" && typeof total === "number") {
    return `${String(queries)} de ${String(total)} consultas`;
  }
  if (typeof channelCount === "number") return `${String(channelCount)} canales sintéticos`;
  return "Sin dato";
}

function videosLink(run: RunOut): string | null {
  if (run.status !== "COMPLETED" && run.status !== "PARTIAL") return null;
  if (run.kind === "vidiq") return "/videos?provider=vidiq_api&sort=breakout&annotated=false";
  if (run.kind === "discovery") return "/videos?provider=youtube_official&annotated=false";
  return null;
}

function RunRow({ run, onResume }: { run: RunOut; onResume: () => void }) {
  const link = videosLink(run);
  return (
    <tr>
      <td>
        <code>{run.id.slice(0, 8)}</code>
      </td>
      <td>{label(run.kind === "vidiq" ? "vidiq" : run.kind)}</td>
      <td>{label(run.status)}</td>
      <td>{formatDateTime(run.started_at)}</td>
      <td>{resultText(run)}</td>
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
        {link && <Link to={link}>Ver videos →</Link>}
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
