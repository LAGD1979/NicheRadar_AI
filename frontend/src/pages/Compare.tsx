import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { ExplorationSteps } from "../components/ExplorationSteps";
import { formatDateTime, formatField } from "../format";
import { MAX_COMPARE, MIN_COMPARE, parseIds } from "../selection";
import type { FieldValue } from "../types";

export function Compare() {
  const [params] = useSearchParams();
  const ids = parseIds(params.get("ids"));
  const valid = ids.length >= MIN_COMPARE && ids.length <= MAX_COMPARE;

  const query = useQuery({
    queryKey: ["compare", ids.join(",")],
    queryFn: () => api.compare(ids),
    enabled: valid,
  });

  return (
    <section aria-labelledby="titulo-comparador">
      <ExplorationSteps current="decide" />
      <h1 id="titulo-comparador">Comparador</h1>
      <p className="hint">
        Compare de {MIN_COMPARE} a {MAX_COMPARE} oportunidades. Cada celda muestra su fuente y su fecha. No se
        marca ganador: la menor saturación no equivale a oportunidad si la demanda no está demostrada.
      </p>

      {!valid && (
        <p role="alert">
          Seleccione entre {MIN_COMPARE} y {MAX_COMPARE} oportunidades en el{" "}
          <Link to="/opportunities">radar</Link>. Tiene {ids.length}.
        </p>
      )}
      {valid && query.isPending && <p>Cargando comparación…</p>}
      {valid && query.isError && <p role="alert">No se pudo comparar: {query.error.message}.</p>}

      {valid && query.isSuccess && (
        <div className="table-wrap">
          <table className="compare">
            <thead>
              <tr>
                <th scope="col">Criterio</th>
                {query.data.items.map((item) => (
                  <th key={item.id} scope="col">
                    <Link to={`/opportunities/${encodeURIComponent(item.id)}`}>{item.title}</Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.data.fields.map((field) => (
                <tr key={field.key}>
                  <th scope="row">
                    {field.label}
                    <small className="muted"> · {field.group}</small>
                  </th>
                  {query.data.items.map((item) => {
                    const values: Partial<Record<string, FieldValue>> = item.values;
                    const v = values[field.key];
                    if (!v) return <td key={item.id}>Sin dato</td>;
                    return (
                      <td key={item.id}>
                        {formatField(v.value, v.state)}
                        {v.state === "AVAILABLE" && v.source && (
                          <small className="muted">
                            <br />
                            {v.source}
                            {v.observed_at ? ` · ${formatDateTime(v.observed_at)}` : ""}
                          </small>
                        )}
                        {v.state !== "AVAILABLE" && v.reason && (
                          <small className="muted">
                            <br />
                            {v.reason}
                          </small>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
