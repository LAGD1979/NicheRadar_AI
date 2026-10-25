import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api";
import { NOT_ENABLED, cell, formatDateTime, formatNumber } from "../format";

export function Summary() {
  const opportunities = useQuery({
    queryKey: ["opportunities", "summary"],
    queryFn: () => api.opportunities(new URLSearchParams({ page_size: "100", sort: "name" })),
  });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });

  const items = opportunities.data?.items ?? [];
  const evaluated = items.filter((o) => o.confidence !== null).length;
  const latestRun = runs.data?.items[0];
  const readyForPilot = items.filter((o) => o.recommendation === "READY_FOR_PILOT").length;
  const validateDemand = items.filter((o) => o.recommendation === "VALIDATE_DEMAND_PILOT").length;

  return (
    <section aria-labelledby="titulo-resumen">
      <h1 id="titulo-resumen">Resumen</h1>
      <p className="hint">
        Cifras de registros internos del demo sintético. Lo que no está habilitado por política se muestra como «{NOT_ENABLED}».
      </p>

      <div className="cards">
        <Card label="Oportunidades" value={opportunities.data ? formatNumber(opportunities.data.total) : "…"} />
        <Card label="Con evaluación" value={opportunities.data ? formatNumber(evaluated) : "…"} />
        <Card label="Listas para piloto" value={opportunities.data ? formatNumber(readyForPilot) : "…"} />
        <Card label="Validar demanda con piloto" value={opportunities.data ? formatNumber(validateDemand) : "…"} />
        <Card label="Puntuación integrada" value={NOT_ENABLED} />
        <Card label="Última corrida" value={latestRun ? cell(latestRun.status) : "Sin corridas"} />
      </div>

      <h2>Oportunidades recientes</h2>
      {opportunities.isError && <p role="alert">No se pudieron cargar las oportunidades.</p>}
      <ul className="list">
        {items.slice(0, 5).map((o) => (
          <li key={o.id}>
            <Link to={`/opportunities/${encodeURIComponent(o.id)}`}>
              {o.niche} · {o.format}
            </Link>{" "}
            <span className="muted">
              Demanda ES: {cell(o.spanish_demand_state)} · Confianza: {cell(o.confidence)}
            </span>
          </li>
        ))}
      </ul>

      <h2>Alertas</h2>
      <ul className="list">
        <li>Búsqueda en español: sin búsquedas reales en el demo; la validación queda pendiente.</li>
        <li>Fuente caducada: una evidencia de «Evidencia internacional» debe refrescarse antes de decidir.</li>
        {config.data?.compliance_mode === "restricted" && (
          <li>Modo restringido: las métricas derivadas y las puntuaciones están bloqueadas.</li>
        )}
      </ul>
      {latestRun && (
        <p className="muted">
          Última corrida: {formatDateTime(latestRun.started_at)} · <Link to="/runs">ver corridas</Link>
        </p>
      )}
    </section>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <span className="card-label">{label}</span>
      <span className="card-value">{value}</span>
    </div>
  );
}
