import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api";

// Alertas abiertas, siempre visibles. Se leen al abrir la página y cuando algo las invalida
// (acusar una alerta, terminar una corrida o «Refrescar saldos»); no se sondean.
export function AlertsBadge() {
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts() });
  if (alerts.isPending || alerts.isError) return null;
  const { open, critical } = alerts.data;
  const level = open === 0 ? "none" : critical > 0 ? "critical" : "warn";
  const text =
    open === 0
      ? "Sin alertas"
      : `${String(open)} ${open === 1 ? "alerta" : "alertas"}${critical > 0 ? ` (${String(critical)} crítica${critical === 1 ? "" : "s"})` : ""}`;
  return (
    <Link
      to="/watchlist#alertas"
      className={`alerts-badge ${level}`}
      title="Alertas abiertas: cuotas, datos por caducar, autorizaciones y cambios en el seguimiento"
    >
      <span aria-hidden="true">{open === 0 ? "○" : "●"}</span> {text}
    </Link>
  );
}
