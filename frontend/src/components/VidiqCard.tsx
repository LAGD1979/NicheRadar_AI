import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { formatNumber } from "../format";
import {
  CREDITS_PER_CALL,
  INITIAL_VIDIQ_FORM,
  MAX_CALLS_LIMIT,
  VIDIQ_CATEGORIES,
  VIDIQ_LANGUAGES,
  VIDIQ_WINDOWS,
  buildVidiqRequest,
  estimatedCredits,
  type VidiqForm,
  type VidiqMode,
} from "../vidiq";

const MODES: Array<{ value: VidiqMode; title: string; text: string }> = [
  { value: "open", title: "Abierto", text: "Sin tema ni formato: lo que más se desvía del promedio de su canal." },
  { value: "format", title: "Por formato", text: "Una forma de contar (ensayo, ranking, guía…), sin fijar el tema." },
  { value: "topic", title: "Por tema", text: "Una palabra clave. Orienta la búsqueda: úsela solo si ya tiene una hipótesis." },
];

export function VidiqCard() {
  const queryClient = useQueryClient();
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const usage = useQuery({ queryKey: ["vidiq-usage"], queryFn: api.vidiqUsage, refetchInterval: 10000 });
  const [form, setForm] = useState<VidiqForm>(INITIAL_VIDIQ_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: api.createRun,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["vidiq-usage"] });
    },
  });

  const configured = providers.data?.find((p) => p.id === "vidiq_api")?.status === "CONFIGURED";
  const capability = capabilities.data?.find((c) => c.id === "vidiq_api");
  const allowed = capability?.allowed === true;
  const ready = configured && allowed;
  const cost = estimatedCredits(form.maxCalls);
  const remaining = usage.data?.credits_remaining;
  const overBudget = remaining !== undefined && cost > remaining;

  function set<K extends keyof VidiqForm>(key: K, value: VidiqForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = buildVidiqRequest(form);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setFormError(null);
    run.mutate(result.body);
  }

  return (
    <article className="source-card" aria-labelledby="vidiq-titulo">
      <header className="source-head">
        <div>
          <h2 id="vidiq-titulo">vidIQ · videos que se desvían del promedio</h2>
          <p className="muted">Encuentra videos de canales pequeños que superan lo habitual en su canal.</p>
        </div>
        <span className={`pill ${ready ? "ok" : "off"}`}>{ready ? "Disponible" : "No disponible"}</span>
      </header>

      {!configured && providers.isSuccess && (
        <p className="notice" role="note">
          Falta la clave de vidIQ. Defina <code>VIDIQ_API_KEY</code> y reinicie la API y el worker.
        </p>
      )}
      {configured && capabilities.isSuccess && !allowed && (
        <p className="notice" role="note">
          Consulta restringida por la compuerta de políticas: {capability?.reason ?? "sin detalle"}.
        </p>
      )}

      <form className="source-form" onSubmit={submit} aria-label="Nueva consulta a vidIQ">
        <fieldset className="modes">
          <legend>¿Cómo quiere explorar?</legend>
          {MODES.map((mode) => (
            <label key={mode.value} className={`mode ${form.mode === mode.value ? "selected" : ""}`}>
              <input
                type="radio"
                name="vidiq-mode"
                value={mode.value}
                checked={form.mode === mode.value}
                onChange={() => { set("mode", mode.value); }}
              />
              <span className="mode-title">{mode.title}</span>
              <span className="mode-text">{mode.text}</span>
            </label>
          ))}
        </fieldset>

        <div className="fields">
          {form.mode === "format" && (
            <label className="wide">
              Formato
              <select value={form.category} onChange={(e) => { set("category", e.target.value); }} required>
                <option value="">Elija un formato…</option>
                {VIDIQ_CATEGORIES.map(([id, text]) => (
                  <option key={id} value={id}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
          )}
          {form.mode === "topic" && (
            <label className="wide">
              Tema
              <input
                type="text"
                value={form.keyword}
                minLength={2}
                maxLength={200}
                required
                onChange={(e) => { set("keyword", e.target.value); }}
                placeholder="p. ej. historia con mapas"
              />
            </label>
          )}
          <label>
            Idioma del título
            <select value={form.language} onChange={(e) => { set("language", e.target.value); }}>
              {VIDIQ_LANGUAGES.map(([code, text]) => (
                <option key={code} value={code}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          <label>
            Publicados
            <select value={form.window} onChange={(e) => { set("window", e.target.value); }}>
              {VIDIQ_WINDOWS.map(([code, text]) => (
                <option key={code} value={code}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          <label>
            Tipo
            <select
              value={form.contentType}
              onChange={(e) => { set("contentType", e.target.value === "short" ? "short" : "long"); }}
            >
              <option value="long">Largo</option>
              <option value="short">Short (solo inglés)</option>
            </select>
          </label>
          <label>
            Suscriptores máx.
            <input
              type="number"
              min={0}
              step={1000}
              value={form.maxSubscribers}
              onChange={(e) => { set("maxSubscribers", Number(e.target.value)); }}
            />
          </label>
          <label>
            Vistas mín.
            <input
              type="number"
              min={0}
              step={10000}
              value={form.minViews}
              onChange={(e) => { set("minViews", Number(e.target.value)); }}
            />
          </label>
          <label>
            Resultados
            <input
              type="number"
              min={1}
              max={50}
              value={form.limit}
              onChange={(e) => { set("limit", Number(e.target.value)); }}
            />
          </label>
          <label>
            Consultas máx.
            <input
              type="number"
              min={1}
              max={MAX_CALLS_LIMIT}
              value={form.maxCalls}
              onChange={(e) => { set("maxCalls", Number(e.target.value)); }}
            />
          </label>
        </div>

        <footer className="source-foot">
          <div className="meter-block">
            <div className="meter-label">
              <span>
                Costo: <strong>{formatNumber(cost)} créditos</strong> ({formatNumber(CREDITS_PER_CALL)} por consulta)
              </span>
              {usage.isSuccess && (
                <span className="muted">
                  Hoy: {formatNumber(usage.data.credits_used)} de {formatNumber(usage.data.credits_daily_limit)}
                </span>
              )}
            </div>
            {usage.isSuccess && (
              <div
                className="meter"
                role="img"
                aria-label={`Créditos usados hoy: ${String(usage.data.credits_used)} de ${String(usage.data.credits_daily_limit)}`}
              >
                <span
                  style={{
                    width: `${String(Math.min(100, (usage.data.credits_used / usage.data.credits_daily_limit) * 100))}%`,
                  }}
                />
              </div>
            )}
            {overBudget && (
              <p className="muted" role="note">
                Excede el tope diario local: la corrida se pausará al agotarlo.
              </p>
            )}
          </div>
          <button type="submit" disabled={!ready || run.isPending}>
            {run.isPending ? "Encolando…" : "Buscar en vidIQ"}
          </button>
        </footer>
      </form>

      {formError && <p role="alert">{formError}</p>}
      {run.isSuccess && (
        <p role="status">
          Consulta encolada. Cuando termine, verá los videos en{" "}
          <Link to="/videos?provider=vidiq_api&sort=breakout&annotated=false">Videos</Link>.
        </p>
      )}
      {run.isError && <p role="alert">No se pudo iniciar la consulta: {run.error.message}.</p>}
      <p className="muted small">
        Los datos de vidIQ y de YouTube caducan a los 29 días. Cada consulta consume créditos de su plan de vidIQ.
      </p>
    </article>
  );
}
