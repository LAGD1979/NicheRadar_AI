import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "../api";
import { balanceLevel, balancePercent, binding, type Balance } from "../balance";
import { formatNumber } from "../format";

interface Meter {
  id: string;
  name: string;
  unit: string;
  configured: boolean;
  balance: Balance | null;
  note: string;
}

const BALANCE_KEYS = [["usage"], ["vidiq-usage"], ["hasdata-usage"], ["alerts"]];
const ACTIVE = new Set(["QUEUED", "RUNNING"]);

// Saldo de cada herramienta, siempre visible. Son los contadores del sistema contra sus topes
// (no el saldo que muestra cada proveedor en su panel): si el proveedor da menos, manda el proveedor.
// Se carga al abrir la página, cuando termina una corrida y con el botón; no sondea.
export function BalanceMeters() {
  const queryClient = useQueryClient();
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const youtube = useQuery({ queryKey: ["usage"], queryFn: api.usage });
  const vidiq = useQuery({ queryKey: ["vidiq-usage"], queryFn: api.vidiqUsage });
  const hasdata = useQuery({ queryKey: ["hasdata-usage"], queryFn: api.hasdataUsage });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });

  const refresh = () => {
    for (const queryKey of BALANCE_KEYS) void queryClient.invalidateQueries({ queryKey });
  };
  const refreshing = youtube.isFetching || vidiq.isFetching || hasdata.isFetching;

  // Una corrida que termina es lo que gasta saldo: al verla terminar se vuelve a leer.
  const finished = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!runs.data) return;
    const done = new Set(runs.data.items.filter((r) => !ACTIVE.has(r.status)).map((r) => r.id));
    const before = finished.current;
    finished.current = done;
    if (before !== null && [...done].some((id) => !before.has(id))) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs.data]);

  const configured = (id: string) => providers.data?.find((p) => p.id === id)?.status === "CONFIGURED";

  const meters: Meter[] = [
    {
      id: "youtube",
      name: "YouTube",
      unit: "unidades",
      configured: configured("youtube_official"),
      balance: youtube.data
        ? { remaining: youtube.data.units_remaining_soft, total: youtube.data.units_budget_soft, period: "hoy" }
        : null,
      note: "Cuota diaria de la API de YouTube (se renueva a medianoche, hora del Pacífico).",
    },
    {
      id: "vidiq",
      name: "vidIQ",
      unit: "créditos",
      configured: configured("vidiq_api"),
      balance: vidiq.data
        ? { remaining: vidiq.data.credits_remaining, total: vidiq.data.credits_daily_limit, period: "hoy" }
        : null,
      note: "Créditos de vidIQ contra el tope diario del sistema.",
    },
    {
      id: "hasdata",
      name: "HasData",
      unit: "consultas",
      configured: configured("google_trends"),
      balance: hasdata.data
        ? binding(
            { remaining: hasdata.data.calls_remaining, total: hasdata.data.calls_daily_limit, period: "hoy" },
            {
              remaining: hasdata.data.calls_month_remaining,
              total: hasdata.data.calls_monthly_limit,
              period: "este mes",
            },
          )
        : null,
      note: "Consultas de Google Trends (10 créditos cada una). Se muestra el tope diario o el mensual, el que se agote primero.",
    },
  ];

  return (
    <div className="balances-wrap">
    <ul className="balances" aria-label="Saldo por herramienta">
      {meters.map((meter) => {
        if (!meter.configured) {
          return (
            <li key={meter.id} className="balance off" title={`${meter.name} no está configurado.`}>
              <span className="balance-name">{meter.name}</span>
              <span className="balance-text">sin configurar</span>
            </li>
          );
        }
        if (meter.balance === null) {
          return (
            <li key={meter.id} className="balance" title={meter.note}>
              <span className="balance-name">{meter.name}</span>
              <span className="balance-text">…</span>
            </li>
          );
        }
        const { remaining, total, period } = meter.balance;
        const level = balanceLevel(remaining, total);
        const text = `${formatNumber(Math.max(0, remaining))} de ${formatNumber(total)} ${meter.unit} · ${period}`;
        return (
          <li key={meter.id} className={`balance ${level}`} title={`${meter.note} Quedan ${text}.`}>
            <span className="balance-name">{meter.name}</span>
            <span
              className="balance-bar"
              role="meter"
              aria-label={`${meter.name}: quedan ${text}`}
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={Math.max(0, remaining)}
            >
              <span style={{ width: `${String(balancePercent(remaining, total))}%` }} />
            </span>
            <span className="balance-text">
              {formatNumber(Math.max(0, remaining))}
              <small> / {formatNumber(total)} · {period}</small>
            </span>
          </li>
        );
      })}
    </ul>
    <button
      type="button"
      className="ghost balance-refresh"
      onClick={refresh}
      disabled={refreshing}
      title="Volver a leer el saldo de cada herramienta"
    >
      {refreshing ? "Actualizando…" : "↻ Refrescar saldos"}
    </button>
    </div>
  );
}
