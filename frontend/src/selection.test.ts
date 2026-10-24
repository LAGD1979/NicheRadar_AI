import { describe, expect, it } from "vitest";

import { MAX_COMPARE, canSelect, isCompareReady, parseIds, toggleSelection } from "./selection";

describe("selección para comparar", () => {
  it("no permite más de 8 oportunidades", () => {
    let selected = new Set<string>();
    for (let i = 0; i < 12; i += 1) {
      selected = toggleSelection(selected, `opp-${String(i)}`);
    }
    expect(selected.size).toBe(MAX_COMPARE);
    expect(canSelect(selected, "otra")).toBe(false);
    expect(canSelect(selected, "opp-0")).toBe(true);
  });

  it("quitar una selección libera un lugar", () => {
    const full = new Set(Array.from({ length: MAX_COMPARE }, (_, i) => `opp-${String(i)}`));
    const after = toggleSelection(full, "opp-0");
    expect(after.size).toBe(MAX_COMPARE - 1);
    expect(canSelect(after, "nueva")).toBe(true);
  });

  it("exige entre 2 y 8 para comparar", () => {
    expect(isCompareReady(["a"])).toBe(false);
    expect(isCompareReady(["a", "b"])).toBe(true);
    expect(isCompareReady(Array.from({ length: 9 }, (_, i) => String(i)))).toBe(false);
  });

  it("parsea ids de la URL sin repetidos ni vacíos", () => {
    expect(parseIds("a, b,,a")).toEqual(["a", "b"]);
    expect(parseIds(null)).toEqual([]);
  });
});
