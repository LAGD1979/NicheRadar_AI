import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api";
import { formatDateTime, formatNumber, label } from "../format";
import type { AlertItem, PilotPlan, WatchChange, WatchEntry } from "../types";

const CHANGE_LABELS: Record<string, string> = {
  confidence: "Confianza",
  recommendation: "Recomendación",
  independent_channels: "Canales independientes",
  replication_state: "Replicación",
  saturation_state: "Saturación en español",
  spanish_demand_state: "Demanda en español",
  independent_signals: "Señales de demanda independientes",
  exact_matches: "Competidores exactos",
  reviewed_matches: "Competidores revisados",
  es_verified_videos: "Videos en español verificados",
};
const ALERT_TYPES: Record<string, string> = {
  QUOTA_WARNING: "Cuota",
  DATA_STALE: "Datos por caducar",
  POLICY_REVIEW_REQUIRED: "Autorización",
  SOURCE_UNAVAILABLE: "Fuente no disponible",
  BACKUP_FAILED: "Backup fallido",
  BACKUP_STALE: "Backup atrasado",
  NEW_INTERNATIONAL_PATTERN: "Patrón internacional",
  SPANISH_DEMAND_SIGNAL: "Demanda en español",
  OPPORTUNITY_CONFIDENCE_UPGRADE: "Confianza",
  SPANISH_COMPETITION_INCREASE: "Competencia en español",
};
const ACTIONS: Record<string, string> = {
  WATCH: "añadida al seguimiento",
  UPDATE: "notas o plan actualizados",
  REVIEWED: "revisada",
  UNWATCH: "quitada del seguimiento",
};
const SEVERITIES: Record<string, string> = { INFO: "Informativa", WARNING: "Aviso", CRITICAL: "Crítica" };
const PRIORITIES: Array<["HIGH" | "MEDIUM" | "LOW", string]> = [
  ["HIGH", "Alta"],
  ["MEDIUM", "Media"],
  ["LOW", "Baja"],
];

function changeValue(value: WatchChange["before"]): string {
  if (value === null) return "sin dato";
  return typeof value === "number" ? formatNumber(value) : label(value);
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function Watchlist() {
  const queryClient = useQueryClient();
  const watchlist = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
  const alerts = useQuery({ queryKey: ["alerts", "all"], queryFn: () => api.alerts(false) });

  const refreshAlerts = () => {
    void queryClient.invalidateQueries({ queryKey: ["alerts"] });
  };
  const acknowledge = useMutation({ mutationFn: api.acknowledgeAlert, onSuccess: refreshAlerts });
  const acknowledgeAll = useMutation({ mutationFn: api.acknowledgeAllAlerts, onSuccess: refreshAlerts });

  return (
    <section aria-labelledby="titulo-seguimiento">
      <h1 id="titulo-seguimiento">Seguimiento</h1>
      <p className="hint">
        Las oportunidades que quiere seguir de cerca. La herramienta las revisa cada semana con los datos que ya
        tiene (sin gastar saldo) y le avisa de los cambios. Los resultados de un piloto los mide y escribe usted:
        aquí no se inventan.
      </p>

      <h2 id="alertas">Alertas</h2>
      {alerts.isPending && <p>Cargando alertas…</p>}
      {alerts.isError && <p role="alert">No se pudieron cargar las alertas.</p>}
      {alerts.isSuccess && alerts.data.items.length === 0 && <p className="empty">No hay alertas abiertas.</p>}
      {alerts.isSuccess && alerts.data.items.length > 0 && (
        <>
          <ul className="alert-list">
            {alerts.data.items.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                busy={acknowledge.isPending}
                onAcknowledge={() => { acknowledge.mutate(alert.id); }}
              />
            ))}
          </ul>
          <button type="button" className="ghost" disabled={acknowledgeAll.isPending} onClick={() => { acknowledgeAll.mutate(); }}>
            Marcar todas como vistas
          </button>
        </>
      )}

      <h2>En seguimiento</h2>
      {watchlist.isPending && <p>Cargando…</p>}
      {watchlist.isError && <p role="alert">No se pudo cargar el seguimiento.</p>}
      {watchlist.isSuccess && watchlist.data.length === 0 && (
        <p className="empty">
          Aún no sigue ninguna oportunidad. Ábrala desde <Link to="/opportunities">Oportunidades</Link> y pulse
          «Añadir a seguimiento».
        </p>
      )}
      {watchlist.isSuccess &&
        watchlist.data.map((entry) => <WatchCard key={entry.opportunity_id} entry={entry} />)}
    </section>
  );
}

function AlertRow({
  alert,
  busy,
  onAcknowledge,
}: {
  alert: AlertItem;
  busy: boolean;
  onAcknowledge: () => void;
}) {
  return (
    <li className={`alert-item ${alert.severity.toLowerCase()}`}>
      <div>
        <strong>{ALERT_TYPES[alert.alert_type] ?? alert.alert_type}</strong>{" "}
        <span className="pill">{SEVERITIES[alert.severity] ?? alert.severity}</span>
        <p>{alert.message}</p>
        <small className="muted">
          {formatDateTime(alert.created_at)}
          {alert.opportunity_id && (
            <>
              {" · "}
              <Link to={`/opportunities/${encodeURIComponent(alert.opportunity_id)}`}>Ver oportunidad</Link>
            </>
          )}
        </small>
      </div>
      <button type="button" className="ghost" disabled={busy} onClick={onAcknowledge}>
        Marcar vista
      </button>
    </li>
  );
}

function WatchCard({ entry }: { entry: WatchEntry }) {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState(entry.notes ?? "");
  const [priority, setPriority] = useState(entry.priority);
  const [plan, setPlan] = useState({
    hypothesis: entry.pilot_plan.hypothesis ?? "",
    videos: (entry.pilot_plan.proposed_videos ?? []).join("\n"),
    metrics: entry.pilot_plan.success_metrics ?? "",
  });
  const [removing, setRemoving] = useState(false);
  const [reason, setReason] = useState("");

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    void queryClient.invalidateQueries({ queryKey: ["alerts"] });
  };
  const save = useMutation({
    mutationFn: () => {
      const pilot: PilotPlan = {
        hypothesis: plan.hypothesis,
        proposed_videos: plan.videos.split("\n").map((v) => v.trim()).filter((v) => v.length > 0),
        success_metrics: plan.metrics,
      };
      return api.updateWatch(entry.opportunity_id, { priority, notes, pilot_plan: pilot });
    },
    onSuccess: refresh,
  });
  const reviewed = useMutation({ mutationFn: () => api.reviewedWatch(entry.opportunity_id, 7), onSuccess: refresh });
  const remove = useMutation({
    mutationFn: () => api.removeWatch(entry.opportunity_id, reason),
    onSuccess: refresh,
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  const videoCount = plan.videos.split("\n").filter((v) => v.trim().length > 0).length;

  return (
    <article className="watch-card" aria-labelledby={`watch-${entry.opportunity_id}`}>
      <header>
        <h3 id={`watch-${entry.opportunity_id}`}>
          <Link to={`/opportunities/${encodeURIComponent(entry.opportunity_id)}`}>
            {entry.niche} · {entry.format}
          </Link>
        </h3>
        <p className="muted">
          {entry.video_type === "SHORT" ? "Corto" : "Largo"} · Estado: {label(entry.status)} · Próxima revisión:{" "}
          {formatDateTime(entry.next_review_at)}
          {entry.review_overdue && <span className="pill off"> Vencida</span>}
          {entry.open_alerts > 0 && <span className="pill ok"> {entry.open_alerts} alerta(s)</span>}
        </p>
      </header>

      <div>
        <strong>Qué cambió desde su última revisión</strong>
        {entry.changes.length === 0 ? (
          <p className="muted">Nada ha cambiado desde {formatDateTime(entry.snapshot_at)}</p>
        ) : (
          <ul>
            {entry.changes.map((c) => (
              <li key={c.key}>
                {CHANGE_LABELS[c.key] ?? c.key}: {changeValue(c.before)} → <strong>{changeValue(c.after)}</strong>
              </li>
            ))}
          </ul>
        )}
        {entry.last_action && (
          <p className="muted small">
            Última decisión: {ACTIONS[entry.last_action.action] ?? entry.last_action.action} · {formatDateTime(entry.last_action.created_at)}
            {entry.last_action.reason ? ` · ${entry.last_action.reason}` : ""}
          </p>
        )}
      </div>

      <form onSubmit={submit} className="watch-form" aria-label={`Notas y plan de ${entry.niche ?? "la oportunidad"}`}>
        <label>
          Prioridad
          <select value={priority} onChange={(e) => { setPriority(e.target.value as WatchEntry["priority"]); }}>
            {PRIORITIES.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <label className="wide-field">
          Notas
          <textarea rows={2} maxLength={2000} value={notes} onChange={(e) => { setNotes(e.target.value); }} />
        </label>
        <details>
          <summary>Plan de piloto (lo escribe y mide usted)</summary>
          <label className="wide-field">
            Hipótesis
            <textarea
              rows={2}
              maxLength={1000}
              value={plan.hypothesis}
              onChange={(e) => { setPlan({ ...plan, hypothesis: e.target.value }); }}
            />
          </label>
          <label className="wide-field">
            Videos originales propuestos (uno por línea, hasta 5)
            <textarea
              rows={3}
              value={plan.videos}
              onChange={(e) => { setPlan({ ...plan, videos: e.target.value }); }}
            />
          </label>
          {videoCount > 5 && <p role="alert">Máximo 5 videos propuestos.</p>}
          <label className="wide-field">
            Métricas de éxito (las medirá en YouTube Studio)
            <textarea
              rows={2}
              maxLength={1000}
              value={plan.metrics}
              onChange={(e) => { setPlan({ ...plan, metrics: e.target.value }); }}
            />
          </label>
        </details>
        <div className="watch-actions">
          <button type="submit" disabled={save.isPending || videoCount > 5}>
            {save.isPending ? "Guardando…" : "Guardar"}
          </button>
          <button type="button" className="ghost" disabled={reviewed.isPending} onClick={() => { reviewed.mutate(); }}>
            Marcar como revisada
          </button>
          <button type="button" className="ghost" onClick={() => { setRemoving(!removing); }}>
            Dejar de seguir
          </button>
        </div>
      </form>

      {removing && (
        <div className="watch-remove">
          <label className="wide-field">
            Motivo (queda registrado)
            <input type="text" value={reason} onChange={(e) => { setReason(e.target.value); }} maxLength={500} />
          </label>
          <button type="button" disabled={remove.isPending || reason.trim().length < 5} onClick={() => { remove.mutate(); }}>
            Confirmar
          </button>
        </div>
      )}
      {save.isError && <p role="alert">{errorText(save.error, "No se pudo guardar.")}</p>}
      {reviewed.isError && <p role="alert">{errorText(reviewed.error, "No se pudo marcar como revisada.")}</p>}
      {remove.isError && <p role="alert">{errorText(remove.error, "No se pudo quitar del seguimiento.")}</p>}
      {save.isSuccess && <p role="status">Guardado.</p>}
    </article>
  );
}
