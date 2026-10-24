import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { formatDateTime, label } from "../format";

export function Runs() {
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const create = useMutation({
    mutationFn: api.createDemoRun,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  return (
    <section aria-labelledby="titulo-corridas">
      <h1 id="titulo-corridas">Corridas</h1>
      <p className="hint">
        Las corridas DEMO leen el dataset sintético. No consultan YouTube ni ningún proveedor externo.
      </p>
      <button type="button" onClick={() => { create.mutate(); }} disabled={create.isPending}>
        {create.isPending ? "Encolando…" : "Iniciar corrida DEMO"}
      </button>
      {create.isSuccess && <p role="status">Corrida encolada. El worker la procesará en segundos.</p>}
      {create.isError && <p role="alert">No se pudo encolar la corrida: {create.error.message}.</p>}

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
                <th scope="col">Cobertura</th>
                <th scope="col">Errores de proveedor</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.items.map((run) => (
                <tr key={run.id}>
                  <td>
                    <code>{run.id.slice(0, 8)}</code>
                  </td>
                  <td>{label(run.kind)}</td>
                  <td>{label(run.status)}</td>
                  <td>{formatDateTime(run.started_at)}</td>
                  <td>
                    {typeof run.coverage.channels === "number"
                      ? `${String(run.coverage.channels)} canales sintéticos`
                      : "Sin dato"}
                  </td>
                  <td>
                    {run.errors.length === 0
                      ? "Ninguno"
                      : run.errors.map((e) => `${String(e.provider)}: ${String(e.code)}`).join("; ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
