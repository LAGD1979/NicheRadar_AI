import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api } from "../api";
import { cell, formatAgeHours, formatField, formatNumber, label, stateFor } from "../format";

export function Videos() {
  const [params, setParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["videos", params.toString()],
    queryFn: () => api.videos(new URLSearchParams(params)),
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }

  return (
    <section aria-labelledby="titulo-videos">
      <h1 id="titulo-videos">Videos</h1>
      <p className="hint">
        Un idioma «Desconocido» con confianza «Conflicto» significa que las señales se contradicen: no se fuerza un idioma.
      </p>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); }} aria-label="Filtros de videos">
        <label>
          Buscar
          <input type="search" value={params.get("q") ?? ""} onChange={(e) => { setParam("q", e.target.value); }} />
        </label>
        <label>
          Tipo
          <select value={params.get("video_type") ?? ""} onChange={(e) => { setParam("video_type", e.target.value); }}>
            <option value="">Todos</option>
            <option value="LONG">Largo</option>
            <option value="SHORT">Short</option>
            <option value="UNKNOWN">Desconocido</option>
          </select>
        </label>
        <label>
          Idioma
          <select value={params.get("language_state") ?? ""} onChange={(e) => { setParam("language_state", e.target.value); }}>
            <option value="">Todos</option>
            <option value="en">Inglés</option>
            <option value="pt">Portugués</option>
            <option value="fr">Francés</option>
            <option value="ja">Japonés</option>
            <option value="UNKNOWN">Desconocido</option>
          </select>
        </label>
      </form>

      {query.isPending && <p>Cargando videos…</p>}
      {query.isError && <p role="alert">No se pudieron cargar los videos: {query.error.message}.</p>}
      {query.isSuccess && query.data.total === 0 && <p className="empty">Sin videos con estos filtros.</p>}
      {query.isSuccess && query.data.total > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Título</th>
                <th scope="col">Canal</th>
                <th scope="col">Suscriptores</th>
                <th scope="col">Tipo</th>
                <th scope="col">Idioma</th>
                <th scope="col">Antigüedad</th>
                <th scope="col">Vistas</th>
                <th scope="col">Origen</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((v) => (
                <tr key={v.id}>
                  <td>{v.title}</td>
                  <td>{v.channel_title}</td>
                  <td>{label(v.subscriber_band)}</td>
                  <td>{cell(v.video_type)}</td>
                  <td>
                    {cell(v.language_state)}
                    {v.language_confidence === "CONFLICT" && <span className="badge warn"> · Conflicto</span>}
                  </td>
                  <td>{formatAgeHours(v.age_hours)}</td>
                  <td>{formatField(v.view_count, stateFor(v.view_count))}</td>
                  <td>{label(v.source_data_type)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">{formatNumber(query.data.total)} videos en total.</p>
        </div>
      )}
    </section>
  );
}
