import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { AnnotatePanel } from "../components/AnnotatePanel";
import { ExplorationSteps } from "../components/ExplorationSteps";
import { cell, daysLeft, formatAgeHours, formatField, formatNumber, label, stateFor } from "../format";
import type { VideoItem } from "../types";

const PAGE_SIZE = 20;

function isSelectable(video: VideoItem): boolean {
  return (video.video_type === "LONG" || video.video_type === "SHORT") && video.availability !== "EXPIRED";
}

export function Videos() {
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<Map<string, VideoItem>>(new Map());
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);

  const query = useQuery({
    queryKey: ["videos", params.toString()],
    queryFn: () => {
      const next = new URLSearchParams(params);
      next.set("page_size", String(PAGE_SIZE));
      return api.videos(next);
    },
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  }

  function toggle(video: VideoItem) {
    setSelected((current) => {
      const next = new Map(current);
      if (next.has(video.id)) next.delete(video.id);
      else next.set(video.id, video);
      return next;
    });
  }

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  return (
    <section aria-labelledby="titulo-videos">
      <ExplorationSteps current="group" />
      <h1 id="titulo-videos">Videos</h1>
      <p className="hint">
        Elija los videos que comparten un mismo formato y agrúpelos en una oportunidad. Un idioma «Desconocido» con
        confianza «Conflicto» significa que las señales se contradicen: no se fuerza un idioma. ¿Aún no hay videos? Empiece
        en <Link to="/runs">Corridas</Link>.
      </p>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); }} aria-label="Filtros de videos">
        <label>
          Buscar
          <input type="search" value={params.get("q") ?? ""} onChange={(e) => { setParam("q", e.target.value); }} />
        </label>
        <label>
          Origen
          <select value={params.get("provider") ?? ""} onChange={(e) => { setParam("provider", e.target.value); }}>
            <option value="">Todos</option>
            <option value="vidiq_api">vidIQ</option>
            <option value="youtube_official">YouTube oficial</option>
            <option value="synthetic_fixture">Demo sintético</option>
          </select>
        </label>
        <label>
          Agrupación
          <select value={params.get("annotated") ?? ""} onChange={(e) => { setParam("annotated", e.target.value); }}>
            <option value="">Todos</option>
            <option value="false">Sin agrupar</option>
            <option value="true">Ya agrupados</option>
          </select>
        </label>
        <label>
          Ordenar por
          <select value={params.get("sort") ?? ""} onChange={(e) => { setParam("sort", e.target.value); }}>
            <option value="">Más recientes</option>
            <option value="breakout">Mayor breakout (vidIQ)</option>
          </select>
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
                <th scope="col">
                  <span className="sr-only">Elegir</span>
                </th>
                <th scope="col">Título</th>
                <th scope="col">Canal</th>
                <th scope="col">Suscriptores</th>
                <th scope="col">Tipo</th>
                <th scope="col">Idioma</th>
                <th scope="col">Antigüedad</th>
                <th scope="col">Vistas</th>
                <th scope="col">Breakout</th>
                <th scope="col">Vistas/hora</th>
                <th scope="col">Origen y vigencia</th>
                <th scope="col">Oportunidad</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((v) => (
                <VideoRow key={v.id} video={v} checked={selected.has(v.id)} onToggle={() => { toggle(v); }} />
              ))}
            </tbody>
          </table>
          <div className="pager">
            <p className="muted">
              {formatNumber(query.data.total)} videos en total · página {page} de {totalPages}
            </p>
            <div>
              <button type="button" className="ghost" disabled={page <= 1} onClick={() => { setParam("page", String(page - 1)); }}>
                Anterior
              </button>
              <button type="button" className="ghost" disabled={page >= totalPages} onClick={() => { setParam("page", String(page + 1)); }}>
                Siguiente
              </button>
            </div>
          </div>
        </div>
      )}

      <AnnotatePanel
        selected={[...selected.values()]}
        onClearSelection={() => { setSelected(new Map()); }}
      />
    </section>
  );
}

function VideoRow({ video: v, checked, onToggle }: { video: VideoItem; checked: boolean; onToggle: () => void }) {
  const metrics = v.provider_metrics?.vidiq;
  const remaining = daysLeft(v.retention_deadline);
  const selectable = isSelectable(v);
  return (
    <tr className={checked ? "row-selected" : undefined}>
      <td>
        <input
          type="checkbox"
          checked={checked}
          disabled={!selectable}
          onChange={onToggle}
          aria-label={`Elegir ${v.title}`}
          title={selectable ? undefined : "Solo se agrupan videos largos o Shorts confirmados y vigentes."}
        />
      </td>
      <td>
        {v.url ? (
          <a href={v.url} target="_blank" rel="noopener noreferrer">
            {v.title}
          </a>
        ) : (
          v.title
        )}
      </td>
      <td>{v.channel_title}</td>
      <td>{label(v.subscriber_band)}</td>
      <td>{cell(v.video_type)}</td>
      <td>
        {cell(v.language_state)}
        {v.language_confidence === "CONFLICT" && <span className="badge warn"> · Conflicto</span>}
      </td>
      <td>{formatAgeHours(v.age_hours)}</td>
      <td>{formatField(v.view_count, stateFor(v.view_count))}</td>
      <td>{metrics ? formatField(metrics.breakout_score, stateFor(metrics.breakout_score)) : "—"}</td>
      <td>{metrics ? formatField(metrics.views_per_hour, stateFor(metrics.views_per_hour)) : "—"}</td>
      <td>
        {label(v.provider)}
        <span className={`vigencia ${remaining !== null && remaining <= 5 ? "soon" : ""}`}>
          {remaining === null ? "" : remaining <= 0 ? "Caducada" : `caduca en ${String(remaining)} días`}
        </span>
      </td>
      <td>
        {v.opportunities.length === 0 ? (
          <span className="muted">Sin agrupar</span>
        ) : (
          <ul className="list-inline">
            {v.opportunities.map((o) => (
              <li key={o.id}>
                <Link to={`/opportunities/${o.id}`}>{o.label}</Link>
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}
