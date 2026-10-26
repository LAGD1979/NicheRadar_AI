import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import { formatNumber } from "../format";
import type { AssistantAnswer, AssistantTurn } from "../types";

// Nombre en lenguaje llano de cada sección del resumen que recibe la IA.
const SECTION_LABELS: Record<string, string> = {
  opportunity: "Oportunidad",
  evaluation: "Evaluación",
  international: "Señal internacional",
  spanish_market: "Mercado español",
  demand: "Demanda",
  competitors: "Competidores",
  production: "Producción",
  scores: "Índices",
  missing: "Lo que falta",
};

const SUGGESTIONS = [
  "¿Qué me falta para poder decidir sobre esta oportunidad?",
  "Explícame el estado actual de la saturación y de la demanda.",
  "¿Qué apoya y qué debilita a esta oportunidad?",
  "¿Cuál sería el siguiente paso más útil y cuánto me costaría?",
];

interface Message {
  role: "user" | "assistant";
  text: string;
  answer?: AssistantAnswer;
}

// Asesor de solo lectura: ve un resumen agregado de la oportunidad (sin títulos, canales ni
// identificadores), cita de dónde sale cada dato y no cambia nada ni decide por la persona.
export function AssistantPanel({ opportunityId }: { opportunityId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [showContext, setShowContext] = useState(false);

  const status = useQuery({ queryKey: ["assistant-status"], queryFn: api.assistantStatus });
  const context = useQuery({
    queryKey: ["assistant-context", opportunityId],
    queryFn: () => api.assistantContext(opportunityId),
    enabled: showContext,
  });

  const ask = useMutation({
    mutationFn: (question: string) => {
      const history: AssistantTurn[] = messages.map((m) => ({ role: m.role, content: m.text }));
      return api.assistantAsk(opportunityId, question, history);
    },
    onSuccess: (answer) => {
      setMessages((current) => [...current, { role: "assistant", text: answer.answer, answer }]);
      void status.refetch();
    },
  });

  function send(question: string) {
    const text = question.trim();
    if (text.length === 0 || ask.isPending) return;
    setMessages((current) => [...current, { role: "user", text }]);
    setDraft("");
    ask.mutate(text);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    send(draft);
  }

  const configured = status.data?.configured === true;
  const last = [...messages].reverse().find((m) => m.answer)?.answer;

  return (
    <section aria-labelledby="asistente-titulo" className="assistant">
      <h3 id="asistente-titulo">Asistente</h3>
      <p className="hint">
        Un asesor que lee el resumen de esta oportunidad y le ayuda a entenderla. <strong>No decide por usted</strong>:
        presenta lo que apoya, lo que debilita y lo que se desconoce. No cambia ningún dato.
      </p>

      <ul className="chips" aria-label="Estado del asistente">
        <li>
          IA: <strong>{configured ? (status.data?.model ?? "configurada") : "no configurada"}</strong>
        </li>
        {status.data && (
          <li>
            Mensajes hoy: <strong>{status.data.messages_used_today}</strong> de {status.data.messages_daily_limit}
          </li>
        )}
        {last && (
          <li title="Estimación: 4 caracteres por token">
            Última consulta: ≈ <strong>{formatNumber(last.context_tokens_estimate)}</strong> tokens enviados
          </li>
        )}
      </ul>

      {status.data && !configured && (
        <p role="alert">
          La IA no está configurada. Defina <code>AI_PROVIDER</code>, la clave del proveedor y <code>AI_MODEL</code> y
          reinicie la API.
        </p>
      )}

      <details
        className="assistant-context"
        onToggle={(e) => { setShowContext(e.currentTarget.open); }}
      >
        <summary>Qué información recibe la IA</summary>
        <p className="muted small">
          Solo conteos, estados, índices y valores que usted escribió. Nunca títulos de videos, nombres de canales,
          identificadores ni enlaces.
        </p>
        {context.isPending && showContext && <p>Cargando…</p>}
        {context.isError && <p role="alert">No se pudo cargar el contexto.</p>}
        {context.data && (
          <>
            <p className="muted small">
              ≈ {formatNumber(context.data.tokens_estimate)} tokens por consulta. Secciones citables:{" "}
              {context.data.sections.map((s) => SECTION_LABELS[s] ?? s).join(", ")}.
            </p>
            <pre className="assistant-json">{JSON.stringify(context.data.context, null, 2)}</pre>
          </>
        )}
      </details>

      <div className="assistant-log" role="log" aria-live="polite" aria-label="Conversación con el asistente">
        {messages.length === 0 && (
          <div className="assistant-empty">
            <p className="muted">Pruebe con una de estas preguntas o escriba la suya:</p>
            <ul className="suggestions">
              {SUGGESTIONS.map((text) => (
                <li key={text}>
                  <button type="button" className="ghost" disabled={!configured || ask.isPending} onClick={() => { send(text); }}>
                    {text}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {messages.map((message, index) => (
          <article key={`${message.role}-${String(index)}`} className={`bubble ${message.role}`}>
            <header>{message.role === "user" ? "Usted" : "Asistente"}</header>
            <p className="bubble-text">{message.text}</p>
            {message.answer && <AnswerExtras answer={message.answer} />}
          </article>
        ))}
        {ask.isPending && (
          <p className="muted" role="status">
            El asistente está leyendo el resumen…
          </p>
        )}
        {ask.isError && (
          <p role="alert">
            {ask.error instanceof ApiError ? ask.error.message : "No se pudo consultar al asistente."}
            {ask.error instanceof ApiError && ask.error.code === "ASSISTANT_LIMIT" && " Vuelva a intentarlo mañana."}
          </p>
        )}
      </div>

      <form onSubmit={submit} aria-label="Preguntar al asistente" className="assistant-form">
        <label className="wide-field">
          Su pregunta
          <textarea
            rows={3}
            maxLength={1000}
            value={draft}
            disabled={!configured}
            onChange={(e) => { setDraft(e.target.value); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                send(draft);
              }
            }}
            placeholder="p. ej. ¿Por qué la saturación sigue en «Desconocida»? (Ctrl+Enter para enviar)"
          />
        </label>
        <div className="assistant-actions">
          <button type="submit" disabled={!configured || ask.isPending || draft.trim().length === 0}>
            {ask.isPending ? "Consultando…" : "Preguntar"}
          </button>
          <button
            type="button"
            className="ghost"
            disabled={messages.length === 0 || ask.isPending}
            onClick={() => {
              setMessages([]);
              ask.reset();
            }}
          >
            Nueva conversación
          </button>
        </div>
      </form>
      <p className="muted small">
        Es una IA: puede equivocarse. Verifique las cifras en las demás pestañas antes de decidir. La conversación no se
        guarda; desaparece al salir de la ficha.
      </p>
    </section>
  );
}

function AnswerExtras({ answer }: { answer: AssistantAnswer }) {
  return (
    <>
      {answer.unsourced && (
        <p className="warn-inline" role="note">
          Esta respuesta trae cifras sin indicar de qué sección salen: verifíquelas antes de usarlas.
        </p>
      )}
      {!answer.structured && (
        <p className="warn-inline" role="note">
          La IA no siguió el formato esperado, así que no hay fuentes ni pasos separados.
        </p>
      )}
      {answer.citations.length > 0 && (
        <p className="citations">
          <span className="muted">Se basa en:</span>{" "}
          {answer.citations.map((c) => (
            <span key={c} className="pill ok">
              {SECTION_LABELS[c] ?? c}
            </span>
          ))}
        </p>
      )}
      {answer.unknowns.length > 0 && (
        <div>
          <strong>Lo que no se sabe</strong>
          <ul>
            {answer.unknowns.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </div>
      )}
      {answer.next_steps.length > 0 && (
        <div>
          <strong>Pasos que podría dar</strong>
          <ul>
            {answer.next_steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
