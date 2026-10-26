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
