import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { SpanishMarket } from "./SpanishMarket";
import { NOT_ENABLED, formatDateTime, formatField, label, stateFor } from "../format";
import type { EvidenceOut, OpportunityDetail as Detail, ScoreOut } from "../types";

const TABS = [
  "Evidencia internacional",
  "Mercado español",
  "Producción IA",
  "Evaluación",
  "Fuente y auditoría",
] as const;
type Tab = (typeof TABS)[number];

export function OpportunityDetail() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: ["opportunity", id], queryFn: () => api.opportunity(id) });
  const [tab, setTab] = useState<Tab>(TABS[0]);

  if (query.isPending) return <p>Cargando ficha…</p>;
  if (query.isError) {
    return (
      <p role="alert">
        No se pudo cargar la oportunidad: {query.error.message}.{" "}
        <Link to="/opportunities">Volver al radar</Link>
      </p>
    );
  }
  const opp = query.data;

  return (
    <article aria-labelledby="titulo-ficha">
      <p className="crumbs">
        <Link to="/opportunities">Oportunidades</Link> / {opp.niche.name}
      </p>
      <h1 id="titulo-ficha">
        {opp.niche.name} · <span className="muted">{opp.format.name}</span>
      </h1>
      <p>
        Estado: <strong>{label(opp.status)}</strong> · Tipo: {label(opp.video_type)} · Idioma destino:{" "}
        {opp.target_lang.toUpperCase()}
        {opp.evaluation && (
          <>
            {" "}· Confianza: <strong>{label(opp.evaluation.confidence)}</strong>
          </>
        )}
      </p>
      <p className="hint">{opp.niche.definition}</p>

      <div role="tablist" aria-label="Secciones de la ficha" className="tabs">
        {TABS.map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            id={`tab-${name}`}
            aria-selected={tab === name}
            aria-controls="panel-ficha"
            onClick={() => { setTab(name); }}
          >
            {name}
          </button>
        ))}
      </div>
      <section id="panel-ficha" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "Evidencia internacional" && <Evidence opp={opp} market="SOURCE_MARKET" />}
        {tab === "Mercado español" && <SpanishMarket opportunityId={opp.id} />}
        {tab === "Producción IA" && <Production opp={opp} />}
        {tab === "Evaluación" && <Evaluation opp={opp} />}
        {tab === "Fuente y auditoría" && <Audit opp={opp} />}
      </section>
    </article>
  );
}

function Evidence({ opp, market }: { opp: Detail; market: string }) {
  const rows = opp.evidence.filter((e) => e.market === market);
  if (rows.length === 0) {
    return (
      <p className="empty">
        {market === "SOURCE_MARKET"
          ? "Sin evidencia internacional registrada para esta oportunidad."
          : "Sin evidencia de mercado español. La ausencia de resultados no prueba oportunidad ni baja competencia."}
      </p>
    );
  }
  return (
    <>
      {market === "SPANISH_MARKET" && <Coverage opp={opp} />}
      <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Rol</th>
            <th scope="col">Título o canal</th>
            <th scope="col">Evidencia</th>
            <th scope="col">Fuerza</th>
            <th scope="col">Disponibilidad</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <EvidenceRow key={e.id} row={e} />
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}

function EvidenceRow({ row }: { row: EvidenceOut }) {
  const expired = row.availability === "EXPIRED";
  return (
    <tr className={expired ? "expired" : undefined}>
      <td>{label(row.role)}</td>
      <td>
        {row.title ?? "Sin título"}
        <br />
        <small>{row.channel_title ?? row.entity_id}</small>
      </td>
      <td>{row.evidence_text}</td>
      <td>{label(row.support_strength)}</td>
      <td>
        {label(row.availability)}
        {expired && <span className="badge warn"> · Refrescar antes de decidir</span>}
      </td>
    </tr>
  );
}

function Coverage({ opp }: { opp: Detail }) {
  const spanish = opp.evaluation?.spanish ?? {};
  const coverage = spanish.query_coverage_count;
  return (
    <p>
      Consultas en español ejecutadas: <strong>{formatField(coverage, stateFor(coverage))}</strong>. La
      cobertura es una muestra descubierta, no el total de competidores.
    </p>
  );
}

function Production({ opp }: { opp: Detail }) {
  const f = opp.evaluation?.feasibility ?? {};
  const scenarios = (f.usd_per_video_scenarios ?? {}) as Record<string, number | null>;
  return (
    <>
      <dl className="facts">
        <dt>Faceless</dt>
        <dd>{label(asText(f.faceless_state))}</dd>
        <dt>Complejidad (1–5)</dt>
        <dd>{formatField(f.complexity_1_to_5 ?? null, stateFor(f.complexity_1_to_5))}</dd>
        <dt>Riesgo de derechos</dt>
        <dd>{label(asText(f.rights_risk))}</dd>
        <dt>Costo por video (USD, estimado)</dt>
        <dd>
          bajo {formatField(scenarios.low ?? null, stateFor(scenarios.low))} · base{" "}
          {formatField(scenarios.base ?? null, stateFor(scenarios.base))} · alto{" "}
          {formatField(scenarios.high ?? null, stateFor(scenarios.high))}
        </dd>
      </dl>
      <h3>Flujo de producción propuesto</h3>
      <p>{opp.format.story_structure}</p>
      <p>
        <strong>Visual:</strong> {opp.format.visual_grammar}
      </p>
      <p>
        <strong>Audio:</strong> {opp.format.audio_grammar}
      </p>
      <p>
        <strong>Activos mínimos:</strong>{" "}
        {formatField(opp.format.min_assets, stateFor(opp.format.min_assets))}
      </p>
      <p className="hint">
        Las estimaciones de costo son de este demo sintético; no son precios de proveedores.
      </p>
    </>
  );
}

function Evaluation({ opp }: { opp: Detail }) {
  if (!opp.evaluation) {
    return <p className="empty">Esta oportunidad aún no tiene evaluación.</p>;
  }
  const ev = opp.evaluation;
  return (
    <>
      <h3>Motivos</h3>
      <ul>
        {ev.reason_codes.map((code) => (
          <li key={code}>{label(code)}</li>
        ))}
      </ul>
      <p>
        Recomendación: <strong>{label(ev.recommendation)}</strong>
      </p>
      <h3>Puntuaciones</h3>
      <ul>
        {Object.entries(ev.scores).map(([name, score]) => (
          <li key={name}>
            {name}: {scoreText(score)}
          </li>
        ))}
      </ul>
    </>
  );
}

// Texto de un campo JSON de la evaluación; si no es texto, no hay dato.
function asText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function scoreText(score: ScoreOut): string {
  return score.state === "RESTRICTED" ? `${NOT_ENABLED} (${score.reason ?? "política"})` : formatField(score.value, score.state);
}

function Audit({ opp }: { opp: Detail }) {
  const ev = opp.evaluation;
  return (
    <dl className="facts">
      <dt>Fuente de la evaluación</dt>
      <dd>{ev ? label(ev.data_source) : "Sin evaluación"}</dd>
      <dt>Observado</dt>
      <dd>{ev ? formatDateTime(ev.observed_at) : "Sin dato"}</dd>
      <dt>Corrida</dt>
      <dd>{ev?.run_id ?? "Sin dato"}</dd>
      <dt>Política de métricas</dt>
      <dd>{ev ? label(ev.metric_policy_state) : "Sin dato"}</dd>
      <dt>Idiomas de origen</dt>
      <dd>{opp.source_languages.join(", ") || "Sin dato"}</dd>
      <dt>Notas del propietario</dt>
      <dd>{opp.owner_notes ?? "Sin notas"}</dd>
    </dl>
  );
}
