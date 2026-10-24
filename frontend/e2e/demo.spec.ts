import { expect, test } from "@playwright/test";

// Tres flujos de M0 contra el stack real (API + base + datos sintéticos). Sin red externa.

test("el demo muestra el banner sintético y el resumen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: "DATOS SINTÉTICOS" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Resumen" })).toBeVisible();
  await expect(page.getByText("No habilitado").first()).toBeVisible();
});

test("el radar abre la ficha con evidencia y pestañas", async ({ page }) => {
  await page.goto("/opportunities");
  await page.getByRole("link", { name: /Historia explicada con mapas/ }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Historia explicada con mapas");
  await page.getByRole("tab", { name: "Mercado español" }).click();
  await expect(page.getByRole("tab", { name: "Mercado español" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Evaluación" }).click();
  await expect(page.getByText("Puntuaciones")).toBeVisible();
});

test("ninguna página principal produce desplazamiento horizontal", async ({ page }, testInfo) => {
  // Las tablas anchas se desplazan dentro de su caja; la página entera no debe hacerlo.
  test.skip(testInfo.project.name !== "mobile", "Solo relevante en viewport de 390 px");
  for (const path of ["/", "/opportunities", "/opportunities/syn-opp-01", "/videos", "/runs", "/settings"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `desplazamiento horizontal en ${path}`).toBeLessThanOrEqual(0);
  }
});

test("comparar cuatro oportunidades muestra columnas y celdas sin ganador", async ({ page }) => {
  await page.goto("/opportunities");
  for (let i = 0; i < 4; i += 1) {
    await page.getByRole("checkbox").nth(i).check();
  }
  await page.getByRole("button", { name: "Comparar seleccionadas" }).click();
  await expect(page).toHaveURL(/\/compare\?ids=/);
  await expect(page.getByRole("columnheader")).toHaveCount(5); // criterio + 4 oportunidades
  await expect(page.getByText("No habilitado").first()).toBeVisible();
});
