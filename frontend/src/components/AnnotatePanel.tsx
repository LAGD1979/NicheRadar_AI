import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { label } from "../format";
import type { VideoItem } from "../types";

const NEW = "__new";

interface Outcome {
  opportunities: string[];
  annotated: number;
  failures: Array<{ title: string; message: string }>;
}

interface Props {
  selected: VideoItem[];
  onClearSelection: () => void;
}

// Panel para agrupar los videos elegidos en una oportunidad (nicho + formato).
// La persona decide qué es un nicho y un formato: la herramienta no lo infiere.
export function AnnotatePanel({ selected, onClearSelection }: Props) {
  const queryClient = useQueryClient();
  const taxonomy = useQuery({ queryKey: ["taxonomy"], queryFn: api.taxonomy });
  const [nicheId, setNicheId] = useState("");
  const [formatId, setFormatId] = useState("");
  const [newNiche, setNewNiche] = useState({ name: "", definition: "" });
  const [newFormat, setNewFormat] = useState({ name: "", story: "", visual: "" });
  const [confidence, setConfidence] = useState("MEDIUM");
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [open, setOpen] = useState(false);

  const save = useMutation({
    mutationFn: async (): Promise<Outcome> => {
      let nId = nicheId;
      let fId = formatId;
      if (nId === NEW) {
        nId = (await api.createNiche({ name: newNiche.name.trim(), definition: newNiche.definition.trim() })).id;
      }
      if (fId === NEW) {
        fId = (
          await api.createFormat({
            name: newFormat.name.trim(),
            story_structure: newFormat.story.trim(),
            visual_grammar: newFormat.visual.trim(),
          })
        ).id;
      }
      const result: Outcome = { opportunities: [], annotated: 0, failures: [] };
      for (const video of selected) {
        try {
          const done = await api.annotateVideo(video.id, {
            niche_id: nId,
            format_id: fId,
            same_format_confidence: confidence,
            rationale: rationale.trim(),
          });
          result.annotated += 1;
          if (!result.opportunities.includes(done.opportunity_id)) result.opportunities.push(done.opportunity_id);
        } catch (failure) {
          result.failures.push({
            title: video.title,
            message: failure instanceof Error ? failure.message : "Error desconocido",
          });
        }
      }
      return result;
    },
    onSuccess: (result) => {
      setOutcome(result);
      if (result.annotated > 0) {
        onClearSelection();
        setOpen(false);
      }
      void queryClient.invalidateQueries({ queryKey: ["videos"] });
      void queryClient.invalidateQueries({ queryKey: ["taxonomy"] });
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (failure) => {
      setError(failure.message);
    },
  });

  if (selected.length === 0 && outcome === null) return null;

  const types = new Set(selected.map((v) => v.video_type));
  const mixed = types.size > 1;

  function problem(): string | null {
    if (!nicheId) return "Elija un nicho o cree uno nuevo.";
    if (!formatId) return "Elija un formato o cree uno nuevo.";
    if (nicheId === NEW && (newNiche.name.trim().length < 3 || newNiche.definition.trim().length < 20)) {
      return "El nicho nuevo necesita un nombre (3+ caracteres) y una definición (20+).";
    }
    if (formatId === NEW && (newFormat.name.trim().length < 3 || newFormat.story.trim().length < 20)) {
      return "El formato nuevo necesita un nombre (3+ caracteres) y cómo se cuenta (20+).";
    }
    if (rationale.trim().length < 10) return "Explique en una frase por qué estos videos comparten formato.";
    return null;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOutcome(null);
    const found = problem();
    setError(found);
    if (found === null) save.mutate();
  }

  return (
    <aside className="annotate" aria-labelledby="agrupar-titulo">
      {selected.length > 0 && !open && (
        <div className="annotate-bar">
          <p>
            <strong>{selected.length}</strong> {selected.length === 1 ? "video elegido" : "videos elegidos"}
          </p>
          <ul className="chips" aria-label="Videos elegidos">
            {selected.slice(0, 3).map((v) => (
              <li key={v.id} title={v.title}>
                {v.title.length > 30 ? `${v.title.slice(0, 30)}…` : v.title}
              </li>
            ))}
            {selected.length > 3 && <li>+{selected.length - 3} más</li>}
          </ul>
          <div className="annotate-actions">
            <button type="button" className="ghost" onClick={onClearSelection}>
              Quitar
            </button>
            <button type="button" onClick={() => { setOpen(true); }}>
              Agrupar en una oportunidad…
            </button>
          </div>
        </div>
      )}
      {selected.length > 0 && open && (
        <form onSubmit={submit}>
          <header className="annotate-head">
            <div>
              <h2 id="agrupar-titulo">Agrupar en una oportunidad</h2>
              <p className="muted">
                {selected.length} {selected.length === 1 ? "video elegido" : "videos elegidos"}. Una oportunidad es un
                nicho (de qué trata) más un formato (cómo se cuenta). Usted decide ambos.
              </p>
            </div>
            <button type="button" className="ghost" onClick={() => { setOpen(false); }}>
              Volver a la lista
            </button>
          </header>

          {mixed && (
            <p className="notice" role="note">
              Hay largos y Shorts en la selección: forman oportunidades distintas y se crearán por separado.
            </p>
          )}

          <div className="annotate-grid">
            <fieldset>
              <legend>1 · Nicho</legend>
              <label>
                Nicho
                <select value={nicheId} onChange={(e) => { setNicheId(e.target.value); }}>
                  <option value="">Elija…</option>
                  {taxonomy.data?.niches.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name}
                    </option>
                  ))}
                  <option value={NEW}>+ Crear nicho nuevo…</option>
                </select>
              </label>
              {nicheId === NEW && (
                <>
                  <label>
                    Nombre
                    <input
                      type="text"
                      maxLength={200}
                      value={newNiche.name}
                      onChange={(e) => { setNewNiche({ ...newNiche, name: e.target.value }); }}
                      placeholder="p. ej. Historia explicada con mapas"
                    />
                  </label>
                  <label>
                    Definición
                    <textarea
                      rows={3}
                      maxLength={1000}
                      value={newNiche.definition}
                      onChange={(e) => { setNewNiche({ ...newNiche, definition: e.target.value }); }}
                      placeholder="De qué trata y qué queda fuera."
                    />
                  </label>
                </>
              )}
            </fieldset>

            <fieldset>
              <legend>2 · Formato</legend>
              <label>
                Formato
                <select value={formatId} onChange={(e) => { setFormatId(e.target.value); }}>
                  <option value="">Elija…</option>
                  {taxonomy.data?.formats.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                  <option value={NEW}>+ Crear formato nuevo…</option>
                </select>
              </label>
              {formatId === NEW && (
                <>
                  <label>
                    Nombre
                    <input
                      type="text"
                      maxLength={200}
                      value={newFormat.name}
                      onChange={(e) => { setNewFormat({ ...newFormat, name: e.target.value }); }}
                      placeholder="p. ej. Ensayo narrado en tres actos"
                    />
                  </label>
                  <label>
                    Cómo se cuenta
                    <textarea
                      rows={3}
                      maxLength={1000}
                      value={newFormat.story}
                      onChange={(e) => { setNewFormat({ ...newFormat, story: e.target.value }); }}
                      placeholder="Estructura de la historia."
                    />
                  </label>
                  <label>
                    Lo que se ve (opcional)
                    <input
                      type="text"
                      maxLength={1000}
                      value={newFormat.visual}
                      onChange={(e) => { setNewFormat({ ...newFormat, visual: e.target.value }); }}
                      placeholder="Mapas, ilustraciones, capturas…"
                    />
                  </label>
                </>
              )}
            </fieldset>

            <fieldset>
              <legend>3 · Evidencia</legend>
              <label>
                ¿Es el mismo formato?
                <select value={confidence} onChange={(e) => { setConfidence(e.target.value); }}>
                  <option value="HIGH">Sí, claramente</option>
                  <option value="MEDIUM">Probablemente</option>
                  <option value="LOW">Con dudas</option>
                </select>
              </label>
              <label>
                Motivo
                <textarea
                  rows={3}
                  maxLength={1000}
                  value={rationale}
                  onChange={(e) => { setRationale(e.target.value); }}
                  placeholder="Qué comparten estos videos."
                />
              </label>
            </fieldset>
          </div>

          <footer className="annotate-foot">
            <ul className="chips" aria-label="Videos que se agrupan">
              {selected.slice(0, 6).map((v) => (
                <li key={v.id} title={v.title}>
                  {v.title.length > 38 ? `${v.title.slice(0, 38)}…` : v.title} · {label(v.video_type)}
                </li>
              ))}
              {selected.length > 6 && <li>+{selected.length - 6} más</li>}
            </ul>
            <button type="submit" disabled={save.isPending}>
              {save.isPending ? "Guardando…" : "Agrupar en oportunidad"}
            </button>
          </footer>
        </form>
      )}

      {error && <p role="alert">{error}</p>}
      {outcome && (
        <div role="status" className="annotate-result">
          <p>
            <strong>{outcome.annotated}</strong> {outcome.annotated === 1 ? "video agrupado" : "videos agrupados"}.
          </p>
          {outcome.opportunities.length > 0 && (
            <p>
              Siguiente paso:{" "}
              {outcome.opportunities.map((id, index) => (
                <span key={id}>
                  {index > 0 && " · "}
                  <Link to={`/opportunities/${id}`}>validar la oportunidad en español →</Link>
                </span>
              ))}
            </p>
          )}
          {outcome.failures.length > 0 && (
            <ul>
              {outcome.failures.map((f) => (
                <li key={f.title} role="alert">
                  No se pudo agrupar «{f.title}»: {f.message}.
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </aside>
  );
}
