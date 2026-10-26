import { describe, expect, it } from "vitest";

import {
  INITIAL_VIDIQ_FORM,
  VIDIQ_CATEGORIES,
  buildVidiqRequest,
  estimatedCredits,
  type VidiqForm,
} from "./vidiq";

function form(over: Partial<VidiqForm>): VidiqForm {
  return { ...INITIAL_VIDIQ_FORM, ...over };
}

describe("buildVidiqRequest", () => {
  it("el modo abierto no envía tema ni formato", () => {
    const result = buildVidiqRequest(form({ mode: "open", category: "reaction", keyword: "gatos" }));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const search = result.body.vidiq.searches[0];
    expect(search).not.toHaveProperty("keyword");
    expect(search).not.toHaveProperty("trend_categories");
    expect(search.max_subscribers).toBe(100000);
  });

  it("el modo por formato exige una categoría conocida", () => {
    expect(buildVidiqRequest(form({ mode: "format", category: "" })).ok).toBe(false);
    expect(buildVidiqRequest(form({ mode: "format", category: "inventada" })).ok).toBe(false);
    const result = buildVidiqRequest(form({ mode: "format", category: "video_essay" }));
    expect(result.ok && result.body.vidiq.searches[0].trend_categories).toEqual(["video_essay"]);
  });

  it("el modo por tema exige entre 2 y 200 caracteres", () => {
    expect(buildVidiqRequest(form({ mode: "topic", keyword: " a " })).ok).toBe(false);
    expect(buildVidiqRequest(form({ mode: "topic", keyword: "x".repeat(201) })).ok).toBe(false);
    const result = buildVidiqRequest(form({ mode: "topic", keyword: " historia " }));
    expect(result.ok && result.body.vidiq.searches[0].keyword).toBe("historia");
  });

  it("los Shorts solo existen en inglés", () => {
    expect(buildVidiqRequest(form({ contentType: "short", language: "es" })).ok).toBe(false);
    expect(buildVidiqRequest(form({ contentType: "short", language: "en" })).ok).toBe(true);
  });

  it("valida los límites numéricos", () => {
    expect(buildVidiqRequest(form({ maxCalls: 0 })).ok).toBe(false);
    expect(buildVidiqRequest(form({ maxCalls: 21 })).ok).toBe(false);
    expect(buildVidiqRequest(form({ limit: 51 })).ok).toBe(false);
    expect(buildVidiqRequest(form({ minViews: -1 })).ok).toBe(false);
  });

  it("estima cinco créditos por consulta", () => {
    expect(estimatedCredits(3)).toBe(15);
  });

  it("no repite identificadores de formato", () => {
    const ids = VIDIQ_CATEGORIES.map(([id]) => id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
