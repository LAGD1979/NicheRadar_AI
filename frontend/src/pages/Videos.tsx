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
      {params.get("run_id") && (
        <p className="hint" role="status">
          Mostrando solo los videos de la corrida <code>{params.get("run_id")?.slice(0, 8)}</code>.{" "}
          <button type="button" className="ghost" onClick={() => { setParam("run_id", ""); }}>
            Ver todos los videos
          </button>
        </p>
      )}
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
      {query.isSuccess && query.data.total === 0 && <p className="empty">
          {params.get("run_id") ? "Esta corrida no trajo videos con estos filtros." : "Sin videos con estos filtros."}
        </p>}
      {query.isSuccess && query.data.total > 0 && (
        <div className="video-results">
          <ul className="video-grid" aria-label="Videos">
            {query.data.items.map((v) => (
              <VideoCard key={v.id} video={v} checked={selected.has(v.id)} onToggle={() => { toggle(v); }} />
            ))}
          </ul>
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

function VideoCard({ video: v, checked, onToggle }: { video: VideoItem; checked: boolean; onToggle: () => void }) {
  const metrics = v.provider_metrics?.vidiq;
  const remaining = daysLeft(v.retention_deadline);
  const selectable = isSelectable(v);
  return (
    <li className={`video-card ${checked ? "selected" : ""}`}>
      <div className="video-media">
        <VideoThumb video={v} />
        <input
          type="checkbox"
          className="video-check"
          checked={checked}
          disabled={!selectable}
          onChange={onToggle}
          aria-label={`Elegir ${v.title}`}
          title={selectable ? undefined : "Solo se agrupan videos largos o Shorts confirmados y vigentes."}
        />
      </div>
      <div className="video-body">
        <h2 className="video-title">
          {v.url ? (
            <a href={v.url} target="_blank" rel="noopener noreferrer">
              {v.title}
            </a>
          ) : (
            v.title
          )}
        </h2>
        <p className="video-channel">{v.channel_title}</p>
        <dl className="video-key">
          <div>
            <dt>Vistas</dt>
            <dd>{formatField(v.view_count, stateFor(v.view_count))}</dd>
          </div>
          <div>
            <dt>Suscriptores</dt>
            <dd>{label(v.subscriber_band)}</dd>
          </div>
        </dl>
        <dl className="video-meta">
          <div>
            <dt>Tipo</dt>
            <dd>{cell(v.video_type)}</dd>
          </div>
          <div>
            <dt>Idioma</dt>
            <dd>
              {cell(v.language_state)}
              {v.language_confidence === "CONFLICT" && <span className="badge warn"> · Conflicto</span>}
            </dd>
          </div>
          <div>
            <dt>Antigüedad</dt>
            <dd>{formatAgeHours(v.age_hours)}</dd>
          </div>
          <div>
            <dt>Breakout</dt>
            <dd>{metrics ? formatField(metrics.breakout_score, stateFor(metrics.breakout_score)) : "—"}</dd>
          </div>
          <div>
            <dt>Vistas/hora</dt>
            <dd>{metrics ? formatField(metrics.views_per_hour, stateFor(metrics.views_per_hour)) : "—"}</dd>
          </div>
          <div>
            <dt>Origen</dt>
            <dd>
              {label(v.provider)}
              <span className={`vigencia ${remaining !== null && remaining <= 5 ? "soon" : ""}`}>
                {remaining === null ? "" : remaining <= 0 ? "Caducada" : `caduca en ${String(remaining)} días`}
              </span>
            </dd>
          </div>
        </dl>
        <div className="video-opps">
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
        </div>
      </div>
    </li>
  );
}

// La miniatura se pide a la CDN pública de YouTube a partir del ID del video: no se guarda nada.
// Los videos de demostración no existen en YouTube, así que no tienen miniatura.
function VideoThumb({ video: v }: { video: VideoItem }) {
  const [failed, setFailed] = useState(false);
  if (v.provider === "synthetic_fixture" || failed) {
    return <div className="thumb-empty">{v.provider === "synthetic_fixture" ? "Demo: sin miniatura" : "Miniatura no disponible"}</div>;
  }
  return (
    <img
      className="thumb"
      src={`https://i.ytimg.com/vi/${encodeURIComponent(v.youtube_video_id)}/mqdefault.jpg`}
      alt={`Miniatura de ${v.title}`}
      width={320}
      height={180}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => { setFailed(true); }}
    />
  );
}
