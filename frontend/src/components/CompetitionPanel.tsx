import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../api";
import { formatNumber, label } from "../format";
import type { CompetitionMatch } from "../types";

const QUALITY_OPTIONS: Array<[string, string]> = [
  ["UNREVIEWED", "Sin revisar"],
  ["EXACT", "Exacto (mismo formato)"],
  ["ADJACENT", "Cercano (no es el mismo)"],
  ["GENERIC", "Genérico"],
  ["FALSE_POSITIVE", "Falso positivo"],
];
const QUALITY_TEXT: Record<string, string> = Object.fromEntries(QUALITY_OPTIONS);
const CONFIDENCE_TEXT: Record<string, string> = { HIGH: "alta", MEDIUM: "media", LOW: "baja" };
const PAGE_SIZE = 25;

type Filter = "pending" | "suggested" | "all";

function percent(value: number | null): string {
  return value === null ? "Sin dato" : `${formatNumber(Math.round(value * 100))} %`;
}

// Revisión de competidores en español: la IA propone y una persona decide.
export function CompetitionPanel({ opportunityId }: { opportunityId: string }) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>("pending");
  const [showNonSpanish, setShowNonSpanish] = useState(false);
  const [page, setPage] = useState(1);

  const competition = useQuery({
    queryKey: ["competition", opportunityId],
    queryFn: () => api.competition(opportunityId),
    refetchInterval: 5000,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["competition", opportunityId] });
    void queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
    void queryClient.invalidateQueries({ queryKey: ["runs"] });
  };
  const review = useMutation({
    mutationFn: ({ id, quality }: { id: string; quality: string }) => api.reviewMatch(id, quality),
    onSuccess: refresh,
  });
  const askAi = useMutation({ mutationFn: () => api.requestAiReview(opportunityId), onSuccess: refresh });
  const accept = useMutation({
    mutationFn: (min: "HIGH" | "MEDIUM") => api.acceptAiSuggestions(opportunityId, min),
    onSuccess: refresh,
  });

  const data = competition.data;
  if (competition.isPending) return <p>Cargando competidores…</p>;
  if (competition.isError || !data) return <p role="alert">No se pudieron cargar los competidores.</p>;

  const coverage = data.coverage;
  const spanish = data.matches.filter((m) => m.is_spanish_market);
  const suggestions = spanish.filter((m) => m.ai_quality && m.match_quality === "UNREVIEWED");
  const high = suggestions.filter((m) => m.ai_confidence === "HIGH").length;
  const mediumUp = suggestions.filter((m) => m.ai_confidence === "HIGH" || m.ai_confidence === "MEDIUM").length;
  const share = coverage.review_share;
  const enough = share !== null && share >= coverage.min_review_share;

  const pool = data.matches.filter((m) => showNonSpanish || m.is_spanish_market);
  const rows = pool.filter((m) => {
    if (filter === "pending") return m.match_quality === "UNREVIEWED";
    if (filter === "suggested") return m.match_quality === "UNREVIEWED" && m.ai_quality !== null;
    return true;
  });
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = rows.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const aiError = askAi.error instanceof ApiError ? askAi.error.message : "No se pudo pedir la sugerencia.";

  return (
    <section aria-labelledby="competidores-titulo" className="competition">
      <h3 id="competidores-titulo">Competidores encontrados</h3>

      <div className="review-meter">
        <p>
          Revisados <strong>{coverage.reviewed_matches}</strong> de <strong>{coverage.es_verified_videos}</strong> videos en
          español ({percent(share)}). Competidores exactos: <strong>{coverage.exact_matches}</strong>.
        </p>
        <div
          className="meter"
          role="img"
          aria-label={`Revisión: ${percent(share)} de los videos en español`}
        >
          <span style={{ width: `${String(Math.min(100, (share ?? 0) * 100))}%` }} />
        </div>
        <p className={enough ? "muted small" : "notice"} role="note">
          {enough
            ? "Cobertura de revisión suficiente para estimar la saturación."
            : `Hasta revisar al menos el ${percent(coverage.min_review_share)} de los videos en español, la saturación queda «Desconocida»: lo que falta por revisar podría ser competencia.`}
        </p>
      </div>

      <div className="toolbar">
        <button
          type="button"
          onClick={() => { askAi.mutate(); }}
          disabled={askAi.isPending || coverage.ai_pending === 0}
          title={coverage.ai_pending === 0 ? "No hay videos pendientes de sugerencia" : undefined}
        >
          {askAi.isPending ? "Encolando…" : `Clasificar con IA (${String(coverage.ai_pending)} pendientes)`}
        </button>
        <button
          type="button"
          className="ghost"
          onClick={() => { accept.mutate("HIGH"); }}
          disabled={accept.isPending || high === 0}
        >
          Aceptar sugerencias de confianza alta ({high})
        </button>
        <button
          type="button"
          className="ghost"
          onClick={() => { accept.mutate("MEDIUM"); }}
          disabled={accept.isPending || mediumUp === 0}
        >
          Aceptar alta y media ({mediumUp})
        </button>
      </div>
      <p className="muted small">
        La IA solo propone, a partir del título y del canal: no ve el video. Una sugerencia no cuenta como revisión
        hasta que usted la acepta, una por una o en bloque.
        {data.ai_assist.agreement !== null && (
          <>
            {" "}
            Coincidencia con su revisión individual: {percent(data.ai_assist.agreement)} (
            {data.ai_assist.agreed} de {data.ai_assist.reviewed_individually}).
          </>
        )}
      </p>
      {askAi.isError && <p role="alert">{aiError}</p>}
      {askAi.isSuccess && (
        <p role="status">Clasificación encolada para {askAi.data.pending} videos. Las sugerencias aparecen al terminar.</p>
      )}
      {accept.isError && <p role="alert">No se pudieron aceptar las sugerencias.</p>}
      {accept.isSuccess && (
        <p role="status">
          {accept.data.accepted} videos pasaron a revisados. Quedan {accept.data.left_for_manual_review} para revisión
          manual.
        </p>
      )}

      <div className="filters" role="group" aria-label="Filtros de competidores">
        <label>
          Mostrar
          <select
            value={filter}
            onChange={(e) => { setFilter(e.target.value as Filter); setPage(1); }}
          >
            <option value="pending">Sin revisar</option>
            <option value="suggested">Sin revisar con sugerencia de la IA</option>
            <option value="all">Todos</option>
          </select>
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={showNonSpanish}
            onChange={(e) => { setShowNonSpanish(e.target.checked); setPage(1); }}
          />
          Incluir los que no cuentan como español
        </label>
      </div>

      {rows.length === 0 ? (
        <p className="empty">
          {data.matches.length === 0 ? "Sin coincidencias todavía." : "Nada que mostrar con este filtro."}
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Video</th>
                <th scope="col">Canal</th>
                <th scope="col">Búsquedas</th>
                <th scope="col">Sugerencia de la IA</th>
                <th scope="col">Revisión</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((match) => (
                <MatchRow
                  key={match.id}
                  match={match}
                  onReview={(quality) => { review.mutate({ id: match.id, quality }); }}
                />
              ))}
            </tbody>
          </table>
          <div className="pager">
            <p className="muted">
              {rows.length} videos · página {current} de {pages}
            </p>
            <div>
              <button type="button" className="ghost" disabled={current <= 1} onClick={() => { setPage(current - 1); }}>
                Anterior
              </button>
              <button type="button" className="ghost" disabled={current >= pages} onClick={() => { setPage(current + 1); }}>
                Siguiente
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function MatchRow({ match, onReview }: { match: CompetitionMatch; onReview: (quality: string) => void }) {
  const hasSuggestion = match.ai_quality !== null;
  const reviewed = match.match_quality !== "UNREVIEWED";
  return (
    <tr>
      <td>
        {match.video_title}
        {!match.is_spanish_market && (
          <small>
            <br />
            {label(match.video_language)} · no cuenta como español
          </small>
        )}
      </td>
      <td>{match.channel_title}</td>
      <td>{match.queries_count}</td>
      <td>
        {hasSuggestion ? (
          <>
            <strong>{QUALITY_TEXT[match.ai_quality ?? ""] ?? match.ai_quality}</strong>{" "}
            <small>(confianza {CONFIDENCE_TEXT[match.ai_confidence ?? ""] ?? "—"})</small>
            <br />
            <small>{match.ai_reason}</small>
            {!reviewed && match.ai_quality && (
              <>
                <br />
                <button type="button" className="ghost" onClick={() => { onReview(match.ai_quality ?? ""); }}>
                  Aceptar
                </button>
              </>
            )}
          </>
        ) : (
          <span className="muted">Sin sugerencia</span>
        )}
      </td>
      <td>
        <select
          aria-label={`Revisión de ${match.video_title}`}
          value={match.match_quality}
          onChange={(e) => { onReview(e.target.value); }}
        >
          {QUALITY_OPTIONS.map(([code, text]) => (
            <option key={code} value={code}>
              {text}
            </option>
          ))}
        </select>
      </td>
    </tr>
  );
}
