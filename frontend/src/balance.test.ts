import { describe, expect, it } from "vitest";

import { balanceLevel, balancePercent, binding } from "./balance";

describe("balance", () => {
  it("clasifica el nivel por lo que queda", () => {
    expect(balanceLevel(90, 100)).toBe("ok");
    expect(balanceLevel(20, 100)).toBe("ok");
    expect(balanceLevel(19, 100)).toBe("low");
    expect(balanceLevel(0, 100)).toBe("empty");
    expect(balanceLevel(-3, 100)).toBe("empty");
  });

  it("calcula el porcentaje sin salirse de 0 a 100", () => {
    expect(balancePercent(45, 90)).toBe(50);
    expect(balancePercent(200, 100)).toBe(100);
    expect(balancePercent(-5, 100)).toBe(0);
    expect(balancePercent(5, 0)).toBe(0);
  });

  it("elige el tope que se agota primero", () => {
    const day = { remaining: 2, total: 15, period: "hoy" };
    const month = { remaining: 80, total: 90, period: "este mes" };
    expect(binding(day, month).period).toBe("hoy");
    expect(binding({ remaining: 14, total: 15, period: "hoy" }, month).period).toBe("este mes");
    expect(binding({ remaining: 3, total: 15, period: "hoy" }, { remaining: 5, total: 90, period: "este mes" }).period).toBe(
      "este mes",
    );
  });
});
