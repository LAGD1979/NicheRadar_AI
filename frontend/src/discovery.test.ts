import { describe, expect, it } from "vitest";

import { buildDiscoveryRequest, estimatedUnits, type DiscoveryForm } from "./discovery";

const base: DiscoveryForm = { language: "es", query: "historia con mapas", window: "0-7", maxSearchCalls: 1 };

describe("buildDiscoveryRequest", () => {
  it("construye el cuerpo que espera la API", () => {
    const result = buildDiscoveryRequest(base);
    expect(result).toEqual({
      ok: true,
      body: {
        kind: "discovery",
        payload: {
          queries: [{ language: "es", query: "historia con mapas", window: "0-7" }],
          max_search_calls: 1,
          pages_per_query: 1,
        },
      },
    });
  });

  it("recorta espacios de la consulta", () => {
    const result = buildDiscoveryRequest({ ...base, query: "  mapas  " });
    expect(result.ok && result.body.payload.queries[0]?.query).toBe("mapas");
  });

  it("rechaza consultas demasiado cortas o largas", () => {
    expect(buildDiscoveryRequest({ ...base, query: " a " }).ok).toBe(false);
    expect(buildDiscoveryRequest({ ...base, query: "x".repeat(201) }).ok).toBe(false);
  });

  it("limita las búsquedas entre 1 y 80", () => {
    expect(buildDiscoveryRequest({ ...base, maxSearchCalls: 0 }).ok).toBe(false);
    expect(buildDiscoveryRequest({ ...base, maxSearchCalls: 81 }).ok).toBe(false);
    expect(buildDiscoveryRequest({ ...base, maxSearchCalls: 2.5 }).ok).toBe(false);
    expect(buildDiscoveryRequest({ ...base, maxSearchCalls: 80 }).ok).toBe(true);
  });
});

describe("estimatedUnits", () => {
  it("multiplica por el costo de search.list (100 unidades)", () => {
    expect(estimatedUnits(1)).toBe(100);
    expect(estimatedUnits(10)).toBe(1000);
  });
});
