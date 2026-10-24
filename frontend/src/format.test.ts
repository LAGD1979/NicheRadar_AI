import { describe, expect, it } from "vitest";

import { NO_DATA, NOT_ENABLED, cell, formatAgeHours, formatField, label } from "./format";

describe("formatField", () => {
  it("muestra NULL como «Sin dato», nunca como cero", () => {
    expect(formatField(null, "NOT_AVAILABLE")).toBe(NO_DATA);
    expect(formatField(undefined, "AVAILABLE")).toBe(NO_DATA);
  });

  it("conserva el cero real como 0", () => {
    expect(formatField(0, "AVAILABLE")).toBe("0");
  });

  it("marca los campos restringidos como no habilitados, sin valor", () => {
    expect(formatField(null, "RESTRICTED")).toBe(NOT_ENABLED);
    expect(formatField(42, "RESTRICTED")).toBe(NOT_ENABLED);
  });

  it("traduce códigos conocidos y deja pasar los desconocidos", () => {
    expect(label("INSUFFICIENT_EVIDENCE")).toBe("Evidencia insuficiente");
    expect(label("CODIGO_NUEVO")).toBe("CODIGO_NUEVO");
  });
});

describe("cell", () => {
  it("convierte cadenas vacías y nulos en «Sin dato»", () => {
    expect(cell(null)).toBe(NO_DATA);
    expect(cell("")).toBe(NO_DATA);
    expect(cell("UNKNOWN")).toBe("Desconocida");
  });
});

describe("formatAgeHours", () => {
  it("usa horas bajo dos días y días después", () => {
    expect(formatAgeHours(null)).toBe(NO_DATA);
    expect(formatAgeHours(1)).toBe("1 h");
    expect(formatAgeHours(96)).toBe("4 días");
  });
});
