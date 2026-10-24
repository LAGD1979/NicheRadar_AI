import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { formatField, label, stateFor } from "../format";

// Un límite ausente se muestra como «Sin dato», no como 0 llamadas.
function formatSoftCap(value: number | undefined): string {
  return formatField(value ?? null, stateFor(value ?? null));
}

export function Settings() {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });

  return (
    <section aria-labelledby="titulo-config">
      <h1 id="titulo-config">Configuración</h1>

      <h2>Parámetros de investigación</h2>
      {config.isPending && <p>Cargando…</p>}
      {config.isError && <p role="alert">No se pudo cargar la configuración.</p>}
      {config.isSuccess && (
        <dl className="facts">
          <dt>Idioma destino</dt>
          <dd>{config.data.target_language.toUpperCase()}</dd>
          <dt>Ventana de publicación</dt>
          <dd>{config.data.lookback_days} días</dd>
          <dt>Regiones en español</dt>
          <dd>{config.data.spanish_regions.join(", ")}</dd>
          <dt>Idiomas de descubrimiento</dt>
          <dd>{config.data.languages.join(", ")}</dd>
          <dt>Modo de cumplimiento</dt>
          <dd>{label(config.data.compliance_mode)}</dd>
          <dt>Zona horaria</dt>
          <dd>{config.data.timezone}</dd>
          <dt>Cuota diaria de búsqueda (referencia)</dt>
          <dd>{formatSoftCap(config.data.quota_soft_caps.youtube_search_daily)} llamadas</dd>
        </dl>
      )}

      <h2>Proveedores</h2>
      {providers.isSuccess && (
        <ul className="list">
          {providers.data.map((p) => (
            <li key={p.id}>
              <strong>{p.name}</strong> · {label(p.status)} · {p.enabled ? "Activo" : "Inactivo"}
              <br />
              <small className="muted">{p.license_note}</small>
            </li>
          ))}
        </ul>
      )}

      <h2>Capacidades condicionadas</h2>
      <p className="hint">
        Estas funciones solo se habilitan con una aprobación registrada. Una variable de entorno no basta.
      </p>
      {capabilities.isSuccess && (
        <ul className="list">
          {capabilities.data.map((c) => (
            <li key={c.id}>
              <strong>{c.label}</strong>: {c.allowed ? "Habilitada" : "No habilitada"}
              <br />
              <small className="muted">{c.reason}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
