// Saldo restante de cada herramienta, para el indicador del encabezado.

export type BalanceLevel = "ok" | "low" | "empty";

export interface Balance {
  remaining: number;
  total: number;
  /** Qué tope manda: «hoy», «este mes»… */
  period: string;
}

export function balanceLevel(remaining: number, total: number): BalanceLevel {
  if (remaining <= 0) return "empty";
  return total > 0 && remaining / total < 0.2 ? "low" : "ok";
}

/** Porcentaje que queda, entre 0 y 100. */
export function balancePercent(remaining: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((remaining / total) * 100)));
}

/** De dos topes, el que se agota primero: es el que el usuario necesita ver. */
export function binding(a: Balance, b: Balance): Balance {
  const ratio = (x: Balance) => (x.total > 0 ? x.remaining / x.total : 0);
  return ratio(b) < ratio(a) ? b : a;
}

/** Cantidades grandes en poco espacio: 850.000 → «850 k», 1.200.000 → «1,2 M». */
export function compactNumber(value: number): string {
  const abs = Math.abs(value);
  const fmt = (n: number) => n.toLocaleString("es-CL", { maximumFractionDigits: 1 });
  if (abs >= 1_000_000) return `${fmt(value / 1_000_000)} M`;
  if (abs >= 1_000) return `${fmt(Math.round(value / 100) / 10)} k`;
  return fmt(value);
}
