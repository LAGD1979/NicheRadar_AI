import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { AssistantPanel } from "../components/AssistantPanel";
import { ExplorationSteps } from "../components/ExplorationSteps";
import { PersistencePanel } from "../components/PersistencePanel";
import { WatchButton } from "../components/WatchButton";
import { ProductionPanel } from "./Production";
import { SpanishMarket } from "./SpanishMarket";
import { NOT_ENABLED, formatDateTime, formatField, label, stateFor } from "../format";
import type { EvidenceOut, OpportunityDetail as Detail, ScoreOut } from "../types";

const TABS = [
  "Evidencia internacional",
  "Mercado español",
  "Producción IA",
  "Evaluación",
  "Asistente",
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
      <ExplorationSteps
        current={tab === "Producción IA" ? "produce" : "validate"}
        onSelect={(key) => {
          if (key === "validate") setTab("Mercado español");
          else if (key === "produce") setTab("Producción IA");
          else return false;
          return true;
        }}
      />
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
      <WatchButton opportunityId={opp.id} />

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
        {tab === "Mercado español" && <SpanishMarket opportunityId={opp.id} smallAccess={opp.evaluation?.spanish.small_channel_access} />}
        {tab === "Producción IA" && (
          <>
            <Production opp={opp} />
            <ProductionPanel opportunityId={opp.id} evaluation={opp.evaluation} />
          </>
        )}
        {tab === "Evaluación" && <Evaluation opp={opp} />}
        {tab === "Asistente" && <AssistantPanel opportunityId={opp.id} />}
        {tab === "Fuente y auditoría" && <Audit opp={opp} />}
      </section>
    </article>
  );
}

const REPLICATION_REASONS: Record<string, string> = {
  NO_RELEVANT_VIDEOS: "No hay videos agrupados con confianza alta o media.",
  SUCCESS_DATA_MISSING: "Faltan vistas o suscriptores para medir el éxito.",
  ONE_CREATOR_GROUP: "Todo viene de un solo canal o creador.",
  SUCCESS_IN_ONE_VIDEO: "El éxito se concentra en un solo video.",
  BELOW_REPLICATED_THRESHOLDS: "Alcanza «prometedor» pero no los umbrales de «replicado».",
  REPLICATION_INSUFFICIENT_SAMPLE: "Muestra insuficiente: faltan canales, videos o semanas.",
  SOME_VIDEOS_MISSING_VIEWS_OR_SUBSCRIBERS: "A algunos videos les faltan vistas o suscriptores.",
  LOW_CONFIDENCE_VIDEOS_EXCLUDED: "Se excluyeron videos agrupados con confianza baja.",
};

function Replication({ opp }: { opp: Detail }) {
  const intl = opp.evaluation?.international ?? {};
  const state = typeof intl.replication_state === "string" ? intl.replication_state : null;
  if (state === null) {
    return (
      <p className="notice" role="note">
        Sin cálculo de replicación. Se calcula al agrupar videos en <Link to="/videos">Videos</Link>, si la política
        de métricas derivadas lo permite.
      </p>
    );
  }
  const reasons = Array.isArray(intl.reason_codes) ? (intl.reason_codes as string[]) : [];
  const num = (key: string) => formatField(intl[key] ?? null, stateFor(intl[key]));
  const concentration =
    typeof intl.top_channel_concentration === "number"
      ? `${String(Math.round(intl.top_channel_concentration * 100))} %`
      : formatField(null, "NOT_AVAILABLE");
  return (
    <section className="replication" aria-label="Replicación internacional">
      <h3>
        Replicación internacional: <strong>{label(state)}</strong>
      </h3>
      <dl className="facts">
        <dt>Canales independientes</dt>
        <dd>{num("independent_channels_observed")}</dd>
        <dt>Videos relevantes</dt>
        <dd>{num("relevant_videos_observed")}</dd>
        <dt>Videos exitosos</dt>
        <dd>{num("successful_videos_observed")}</dd>
        <dt>Semanas distintas</dt>
        <dd>{num("distinct_weeks")}</dd>
        <dt>Concentración del mayor canal</dt>
        <dd>{concentration}</dd>
      </dl>
      {reasons.length > 0 && (
        <ul className="list">
          {reasons.map((code) => (
            <li key={code}>{REPLICATION_REASONS[code] ?? code}</li>
          ))}
        </ul>
      )}
      <p className="muted small">
        Reglas heurísticas por calibrar. Un canal distinto no prueba un creador distinto (canales espejo sin revisar), y
        los videos salen de búsquedas y de su selección: no son una muestra del universo de YouTube.
      </p>
    </section>
  );
}

function Evidence({ opp, market }: { opp: Detail; market: string }) {
  const rows = opp.evidence.filter((e) => e.market === market);
  if (rows.length === 0) {
    return (
      <>
        {market === "SOURCE_MARKET" && <Replication opp={opp} />}
        {market === "SOURCE_MARKET" && <PersistencePanel opp={opp} />}
        <p className="empty">
          {market === "SOURCE_MARKET"
            ? "Sin evidencia internacional registrada para esta oportunidad."
            : "Sin evidencia de mercado español. La ausencia de resultados no prueba oportunidad ni baja competencia."}
        </p>
      </>
    );
  }
  return (
    <>
      {market === "SOURCE_MARKET" && <Replication opp={opp} />}
      {market === "SOURCE_MARKET" && <PersistencePanel opp={opp} />}
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

// Un índice sin dato muestra su motivo (qué dimensión falta); nunca se muestra como 0.
function scoreText(score: ScoreOut): string {
  if (score.state === "RESTRICTED") {
    return `${NOT_ENABLED} (${score.reason ?? "política"})`;
  }
  if (score.value === null) {
    return `Sin dato${score.reason ? ` (${score.reason})` : ""}`;
  }
  return formatField(score.value, score.state);
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
