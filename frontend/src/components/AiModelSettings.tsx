import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../api";
import { compactNumber } from "../balance";
import type { AiFunctionSetting, AiModelOption } from "../types";

const DEFAULT_VALUE = "";

function optionValue(option: Pick<AiModelOption, "provider" | "model">): string {
  return `${option.provider}|${option.model}`;
}

const PROVIDER_NAMES: Record<string, string> = { anthropic: "Anthropic", openai: "OpenAI" };
const FUNCTION_NAMES: Record<string, string> = {
  assistant: "asistente",
  classification: "clasificación",
  plan: "plan",
};

// Elige la IA y el modelo de cada función. Sin elección rige el valor del entorno (.env).
export function AiModelSettings() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["ai-settings"], queryFn: api.aiSettings });
  const usage = useQuery({ queryKey: ["ai-usage"], queryFn: api.aiUsage });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    void queryClient.invalidateQueries({ queryKey: ["assistant-status"] });
  };
  const choose = useMutation({
    mutationFn: ({ fn, value }: { fn: string; value: string }) => {
      if (value === DEFAULT_VALUE) return api.clearAiSetting(fn);
      const cut = value.indexOf("|");
      return api.setAiSetting(fn, value.slice(0, cut), value.slice(cut + 1));
    },
    onSuccess: refresh,
  });

  if (settings.isPending) return <p>Cargando la configuración de IA…</p>;
  if (settings.isError) return <p role="alert">No se pudo leer la configuración de IA.</p>;

  const { functions, catalog, default: fallback } = settings.data;
  const providers = [...new Set(catalog.map((c) => c.provider))];
  const fallbackText = fallback.model
    ? `${PROVIDER_NAMES[fallback.provider] ?? fallback.provider} · ${fallback.model}`
    : "sin IA";

  return (
    <div className="ai-settings">
      <p className="hint">
        Cada función puede usar un modelo distinto: uno rápido y económico para tareas masivas y uno más capaz para
        razonar. El cambio rige en la próxima consulta, sin reiniciar. Los proveedores sin clave aparecen
        deshabilitados.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Función</th>
              <th scope="col">Modelo</th>
              <th scope="col">Vigente</th>
            </tr>
          </thead>
          <tbody>
            {functions.map((fn) => (
              <FunctionRow
                key={fn.id}
                fn={fn}
                providers={providers}
                catalog={catalog}
                fallbackText={fallbackText}
                busy={choose.isPending}
                onChange={(value) => { choose.mutate({ fn: fn.id, value }); }}
              />
            ))}
          </tbody>
        </table>
      </div>
      {choose.isError && (
        <p role="alert">
          {choose.error instanceof ApiError ? choose.error.message : "No se pudo guardar la elección."}
        </p>
      )}
      {usage.data && (
        <p className="muted small">
          Tokens de IA hoy: <strong>{compactNumber(usage.data.tokens_used)}</strong> de{" "}
          {compactNumber(usage.data.tokens_daily_limit)} (tope por corrida: {compactNumber(usage.data.tokens_run_limit)}).
          {Object.keys(usage.data.by_function).length > 0 && (
            <> Por función: {Object.entries(usage.data.by_function).map(([fn, n]) => `${FUNCTION_NAMES[fn] ?? fn} ${compactNumber(n)}`).join(" · ")}.</>
          )}{" "}
          Son tokens reales que informa el proveedor; al llegar al tope la IA se detiene y conserva lo ya hecho.
        </p>
      )}
      <details>
        <summary>Qué hace cada modelo</summary>
        <ul className="list">
          {catalog.map((c) => (
            <li key={optionValue(c)}>
              <strong>{c.label}</strong> <small className="muted">({PROVIDER_NAMES[c.provider] ?? c.provider}
              {c.available ? "" : ", sin clave"})</small>
              <br />
              <small className="muted">{c.description}</small>
            </li>
          ))}
        </ul>
        <p className="muted small">La lista se edita en <code>config/research.yaml</code> (sección <code>ai</code>).</p>
      </details>
    </div>
  );
}

function FunctionRow({
  fn,
  providers,
  catalog,
  fallbackText,
  busy,
  onChange,
}: {
  fn: AiFunctionSetting;
  providers: string[];
  catalog: AiModelOption[];
  fallbackText: string;
  busy: boolean;
  onChange: (value: string) => void;
}) {
  const current = fn.source === "user" && fn.model ? `${fn.provider}|${fn.model}` : DEFAULT_VALUE;
  const labelId = `ai-fn-${fn.id}`;
  return (
    <tr>
      <th scope="row">
        <span id={labelId}>{fn.label}</span>
        <br />
        <small className="muted">{fn.description}</small>
        <br />
        <small className="muted">{fn.suggestion}</small>
      </th>
      <td>
        <select
          aria-labelledby={labelId}
          value={current}
          disabled={busy}
          onChange={(e) => { onChange(e.target.value); }}
        >
          <option value={DEFAULT_VALUE}>Predeterminado ({fallbackText})</option>
          {providers.map((provider) => (
            <optgroup key={provider} label={PROVIDER_NAMES[provider] ?? provider}>
              {catalog
                .filter((c) => c.provider === provider)
                .map((c) => (
                  <option key={optionValue(c)} value={optionValue(c)} disabled={!c.available}>
                    {c.label}
                    {c.available ? "" : " (sin clave)"}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </td>
      <td>
        {fn.configured && fn.model ? (
          <>
            <strong>{fn.model}</strong> <small className="muted">· {PROVIDER_NAMES[fn.provider] ?? fn.provider}</small>
          </>
        ) : (
          <span className="muted">IA no configurada</span>
        )}
      </td>
    </tr>
  );
}
