import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../api";
import { formatDateTime, label } from "../format";
import type { SchedulerJob } from "../types";

const INTERVALS: Array<[number, string]> = [
  [1, "cada hora"],
  [6, "cada 6 horas"],
  [12, "cada 12 horas"],
  [24, "cada día"],
  [72, "cada 3 días"],
  [168, "cada semana"],
  [336, "cada 2 semanas"],
  [720, "cada 30 días"],
];

function intervalOptions(current: number): Array<[number, string]> {
  return INTERVALS.some(([hours]) => hours === current)
    ? INTERVALS
    : [...INTERVALS, [current, `cada ${String(current)} horas`]].sort((a, b) => Number(a[0]) - Number(b[0])) as Array<[number, string]>;
}

// Trabajos recurrentes de la aplicación. Solo hay trabajos sin costo externo: lo que gasta cuota
// o créditos se sigue iniciando a mano desde Corridas y desde cada oportunidad.
export function JobsPanel() {
  const queryClient = useQueryClient();
  const jobs = useQuery({ queryKey: ["scheduler-jobs"], queryFn: api.schedulerJobs });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["scheduler-jobs"] });
    void queryClient.invalidateQueries({ queryKey: ["runs"] });
  };
  const update = useMutation({
    mutationFn: ({ job, body }: { job: string; body: { enabled?: boolean; interval_hours?: number } }) =>
      api.updateJob(job, body),
    onSuccess: refresh,
  });
  const run = useMutation({ mutationFn: api.runJob, onSuccess: refresh });

  if (jobs.isPending) return <p>Cargando trabajos…</p>;
  if (jobs.isError) return <p role="alert">No se pudieron cargar los trabajos programados.</p>;

  return (
    <div>
      <p className="hint">
        Se ejecutan solos mientras la aplicación esté en marcha, en el mismo proceso que las corridas. Solo son
        trabajos sin costo externo: no gastan cuota de YouTube ni créditos de vidIQ, HasData o IA.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Trabajo</th>
              <th scope="col">Activo</th>
              <th scope="col">Frecuencia</th>
              <th scope="col">Última ejecución</th>
              <th scope="col">Próxima</th>
              <th scope="col">Acción</th>
            </tr>
          </thead>
          <tbody>
            {jobs.data.map((job) => (
              <JobRow
                key={job.job_type}
                job={job}
                busy={update.isPending || run.isPending}
                onToggle={(enabled) => { update.mutate({ job: job.job_type, body: { enabled } }); }}
                onInterval={(hours) => { update.mutate({ job: job.job_type, body: { interval_hours: hours } }); }}
                onRun={() => { run.mutate(job.job_type); }}
              />
            ))}
          </tbody>
        </table>
      </div>
      {(update.isError || run.isError) && (
        <p role="alert">
          {update.error instanceof ApiError
            ? update.error.message
            : run.error instanceof ApiError
              ? run.error.message
              : "No se pudo completar la acción."}
        </p>
      )}
      {run.isSuccess && <p role="status">Ejecución encolada: la verá en Corridas.</p>}
    </div>
  );
}

function JobRow({
  job,
  busy,
  onToggle,
  onInterval,
  onRun,
}: {
  job: SchedulerJob;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onInterval: (hours: number) => void;
  onRun: () => void;
}) {
  const id = `job-${job.job_type}`;
  return (
    <tr>
      <th scope="row">
        <span id={id}>{job.label}</span>
        <br />
        <small className="muted">{job.description}</small>
      </th>
      <td>
        <input
          type="checkbox"
          aria-labelledby={id}
          checked={job.enabled}
          disabled={busy}
          onChange={(e) => { onToggle(e.target.checked); }}
        />
      </td>
      <td>
        <select
          aria-label={`Frecuencia de ${job.label}`}
          value={job.interval_hours}
          disabled={busy}
          onChange={(e) => { onInterval(Number(e.target.value)); }}
        >
          {intervalOptions(job.interval_hours).map(([hours, text]) => (
            <option key={hours} value={hours}>
              {text}
            </option>
          ))}
        </select>
      </td>
      <td>
        {job.last_run_at ? (
          <>
            {formatDateTime(job.last_run_at)}
            {job.last_status && <small className="muted"> · {label(job.last_status)}</small>}
          </>
        ) : (
          <span className="muted">Nunca</span>
        )}
      </td>
      <td>{job.enabled ? formatDateTime(job.next_run_at) : <span className="muted">Desactivado</span>}</td>
      <td>
        <button type="button" className="ghost" disabled={busy} onClick={onRun}>
          Ejecutar ahora
        </button>
      </td>
    </tr>
  );
}
