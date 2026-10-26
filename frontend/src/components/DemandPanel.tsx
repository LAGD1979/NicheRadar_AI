import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { formatDateTime, formatNumber, label } from "../format";
import type { DemandSignal } from "../types";

const GEOS: Array<[string, string]> = [
  ["", "Todos los países"],
  ["ES", "España"],
  ["MX", "México"],
  ["AR", "Argentina"],
  ["CO", "Colombia"],
  ["CL", "Chile"],
  ["PE", "Perú"],
];
const MAX_KEYWORDS = 5;
const HASDATA_CREDITS = 10;
const VIDIQ_CREDITS = 5;
const FAMILY_ORDER = ["google_trends", "vidiq_keywords", "youtube_consumption"];

function parseKeywords(text: string): string[] {
  const unique = new Map<string, string>();
  for (const part of text.split(/[\n,]/)) {
    const word = part.trim();
    if (word.length > 0 && !unique.has(word.toLowerCase())) unique.set(word.toLowerCase(), word);
  }
  return [...unique.values()];
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function detail(signal: DemandSignal): string {
  const d = signal.details ?? {};
  if (signal.family === "google_trends") {
    const recent = num(d.recent_mean);
    const base = num(d.base_mean);
    const share = num(d.share_of_leader);
    if (recent === null) return `${String(num(d.weeks_with_data) ?? 0)} semanas con dato: insuficiente`;
    const others = Array.isArray(d.terms) ? d.terms.length - 1 : 0;
    const comparison =
      others > 0
      ? ` · comparado con ${String(others)} término(s)${share === null ? "" : `: ${formatNumber(share)} % del más fuerte`}`
      : "";
    return `Índice relativo reciente ${formatNumber(recent)} de 100${base === null ? "" : ` (base ${formatNumber(base)})`}${comparison}`;
  }
  if (signal.family === "vidiq_keywords") {
    const monthly = num(d.monthly_searches);
    const growth = num(d.growth_pct);
    if (monthly === null) return "Volumen desconocido";
    return `${formatNumber(monthly)} búsquedas al mes${growth === null ? "" : ` · ${growth > 0 ? "+" : ""}${formatNumber(growth)} %`}`;
  }
  return `${String(num(d.strong_competitors) ?? 0)} de ${String(num(d.exact_competitors) ?? 0)} competidores exactos con vistas altas`;
}

// Mide la demanda con fuentes externas. Cada medida caduca a los 29 días.
export function DemandPanel({ opportunityId }: { opportunityId: string }) {
  const queryClient = useQueryClient();
  const [keywords, setKeywords] = useState("");
  const [geo, setGeo] = useState("");
  const [trends, setTrends] = useState(true);
  const [vidiq, setVidiq] = useState(true);
  const [related, setRelated] = useState(false);
  const [force, setForce] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const demand = useQuery({
    queryKey: ["demand", opportunityId],
    queryFn: () => api.demand(opportunityId),
    refetchInterval: 8000,
  });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const usage = useQuery({ queryKey: ["hasdata-usage"], queryFn: api.hasdataUsage });

  const run = useMutation({
    mutationFn: () =>
      api.requestDemand(opportunityId, {
        keywords: parseKeywords(keywords),
        geo: geo || null,
        sources: [...(trends ? ["trends"] : []), ...(vidiq ? ["vidiq"] : [])],
        include_related: related,
        force,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["hasdata-usage"] });
      void queryClient.invalidateQueries({ queryKey: ["vidiq-usage"] });
    },
  });

  const providerOk = (id: string) => providers.data?.find((p) => p.id === id)?.status === "CONFIGURED";
  const capabilityOk = (id: string) => capabilities.data?.find((c) => c.id === id)?.allowed === true;
  const trendsReady = providerOk("google_trends") && capabilityOk("google_trends");
  const vidiqReady = providerOk("vidiq_api") && capabilityOk("vidiq_api");

  const list = parseKeywords(keywords);
  // Los términos van juntos en una sola llamada (sus índices quedan comparables);
  // las consultas relacionadas cuestan una llamada por término.
  const hasdataCalls = trends && list.length > 0 ? 1 + (related ? list.length : 0) : 0;
  const vidiqCalls = vidiq ? list.length : 0;

  function problem(): string | null {
    if (list.length === 0) return "Escriba al menos una palabra clave.";
    if (list.length > MAX_KEYWORDS) return `Máximo ${String(MAX_KEYWORDS)} palabras clave por medición.`;
    if (list.some((w) => w.length < 2 || w.length > 80)) return "Cada palabra clave debe tener entre 2 y 80 caracteres.";
    if (!trends && !vidiq) return "Elija al menos una fuente.";
    if (trends && !trendsReady) return "Google Trends (HasData) no está disponible: revise la clave y la política.";
    if (vidiq && !vidiqReady) return "vidIQ no está disponible: revise la clave y la política.";
    return null;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = problem();
    setFormError(found);
    if (found === null) run.mutate();
  }

  const data = demand.data;
  const ordered = [...(data?.signals ?? [])].sort(
    (a, b) => FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family),
  );

  return (
    <section aria-labelledby="demanda-titulo" className="demand">
      <h3 id="demanda-titulo">Demanda en español</h3>
      <p className="hint">
        La demanda es «Observada» con al menos dos señales de fuentes distintas. Varias palabras clave de una misma
        fuente cuentan una vez, y la falta de datos nunca se toma como falta de demanda. Los términos de una
        misma medición se piden juntos, así que sus índices son comparables entre sí.
      </p>

      {data && (
        <>
          <p>
            Señales independientes presentes: <strong>{data.independent_signals}</strong>{" "}
            {data.present_families.length > 0 && <>({data.present_families.map((f) => label(f)).join(" + ")})</>}
          </p>
          <ul className="chips" aria-label="Estado por fuente">
            {FAMILY_ORDER.map((family) => (
              <li key={family}>
                {label(family)}: <strong>{label(data.family_states[family] ?? "UNKNOWN")}</strong>
              </li>
            ))}
          </ul>
          {ordered.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Fuente</th>
                    <th scope="col">Palabra clave</th>
                    <th scope="col">País</th>
                    <th scope="col">Resultado</th>
                    <th scope="col">Detalle</th>
                    <th scope="col">Medido</th>
                  </tr>
                </thead>
                <tbody>
                  {ordered.map((s, i) => (
                    <tr key={`${s.family}-${s.keyword ?? ""}-${s.geo ?? ""}-${String(i)}`}>
                      <td>{label(s.family)}</td>
                      <td>{s.keyword || "—"}</td>
                      <td>{s.geo || (s.keyword ? "Todos" : "—")}</td>
                      <td>{label(s.state)}</td>
                      <td>{detail(s)}</td>
                      <td>
                        {s.observed_at ? formatDateTime(s.observed_at) : "—"}
                        {s.expires_at && <small> · caduca {formatDateTime(s.expires_at)}</small>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <form onSubmit={submit} aria-label="Medir demanda" className="filters">
        <label className="wide-field">
          Palabras clave (una por línea, hasta {MAX_KEYWORDS})
          <textarea
            rows={3}
            value={keywords}
            onChange={(e) => { setKeywords(e.target.value); }}
            placeholder={"video ensayo\nanálisis de series"}
          />
        </label>
        <label>
          País
          <select value={geo} onChange={(e) => { setGeo(e.target.value); }}>
            {GEOS.map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="checks">
          <legend>Fuentes</legend>
          <label className={trendsReady ? undefined : "disabled"}>
            <input type="checkbox" checked={trends} disabled={!trendsReady} onChange={(e) => { setTrends(e.target.checked); }} />
            Google Trends (HasData)
          </label>
          <label className={vidiqReady ? undefined : "disabled"}>
            <input type="checkbox" checked={vidiq} disabled={!vidiqReady} onChange={(e) => { setVidiq(e.target.checked); }} />
            Palabras clave (vidIQ)
          </label>
          <label className={trendsReady ? undefined : "disabled"}>
            <input type="checkbox" checked={related} disabled={!trendsReady || !trends} onChange={(e) => { setRelated(e.target.checked); }} />
            Incluir consultas relacionadas
          </label>
          <label className={trendsReady ? undefined : "disabled"}>
            <input type="checkbox" checked={force} disabled={!trendsReady || !trends} onChange={(e) => { setForce(e.target.checked); }} />
            Repetir aunque haya una medición reciente
          </label>
        </fieldset>
        <button type="submit" disabled={run.isPending}>
          {run.isPending ? "Encolando…" : "Medir demanda"}
        </button>
      </form>
      <p className="muted small">
        Costo estimado: {hasdataCalls} {hasdataCalls === 1 ? "consulta" : "consultas"} a HasData ({formatNumber(hasdataCalls * HASDATA_CREDITS)} créditos de
        HasData) y {formatNumber(vidiqCalls * VIDIQ_CREDITS)} créditos de vidIQ.
        {usage.data && (
          <>
            {" "}Hoy: {usage.data.calls_used} de {usage.data.calls_daily_limit} consultas a HasData; este mes:{" "}
            {usage.data.calls_month_used} de {usage.data.calls_monthly_limit}.
          </>
        )}{" "}
        El índice de Google Trends es relativo (0 a 100), no un volumen de búsquedas.
      </p>
      {formError && <p role="alert">{formError}</p>}
      {run.isError && (
        <p role="alert">{run.error instanceof ApiError ? run.error.message : "No se pudo iniciar la medición."}</p>
      )}
      {run.isSuccess && (
        <p role="status">Medición encolada. Los resultados aparecen aquí al terminar; el estado se actualiza solo.</p>
      )}
    </section>
  );
}
