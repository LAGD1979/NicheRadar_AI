import { expect, test } from "@playwright/test";

// Tres flujos de M0 contra el stack real (API + base + datos sintéticos). Sin red externa.

test("el demo muestra el banner sintético y el resumen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: /DATOS (SINTÉTICOS|MIXTOS)/ })).toBeVisible();
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
  for (const path of ["/", "/opportunities", "/opportunities/syn-opp-01", "/videos", "/runs", "/watchlist", "/settings"]) {
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
  // La fila del índice existe en ambos modos; su valor depende de la compuerta de políticas.
  await expect(page.getByRole("rowheader", { name: /Índice integrado/ })).toBeVisible();
});

test("la ruta de exploración guía de Corridas a Videos y ofrece agrupar", async ({ page }) => {
  await page.goto("/runs");
  await expect(page.getByRole("navigation", { name: "Ruta de exploración" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /vidIQ/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /YouTube · búsqueda por consulta/ })).toBeVisible();

  await page.goto("/videos");
  await expect(page.getByRole("navigation", { name: "Ruta de exploración" })).toBeVisible();
  await page.locator('.video-card input[type="checkbox"]:not([disabled])').first().check();
  await expect(page.getByText(/1 video elegido/)).toBeVisible();
  await page.getByRole("button", { name: /Agrupar en una oportunidad/ }).click();
  await expect(page.getByRole("heading", { name: "Agrupar en una oportunidad" })).toBeVisible();
  // Sin guardar nada: no se envía el formulario.
});

test("la ficha ofrece medir demanda y persistencia sin enviar nada", async ({ page }) => {
  await page.goto("/opportunities/syn-opp-01");
  await page.getByRole("tab", { name: "Mercado español" }).click();
  await expect(page.getByRole("heading", { name: "Demanda en español" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Medir demanda" })).toBeVisible();
  await expect(page.getByText(/no un volumen de búsquedas/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Competidores encontrados" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Clasificar con IA/ })).toBeVisible();
  await expect(page.getByText(/La IA solo propone/)).toBeVisible();
  await page.getByRole("tab", { name: "Evidencia internacional" }).click();
  await expect(page.getByRole("button", { name: /Medir persistencia/ })).toBeVisible();
  // Sin enviar los formularios: no se gastan créditos.
});

test("en la ficha, los pasos 3 y 4 de la ruta cambian de pestaña", async ({ page }) => {
  await page.goto("/opportunities/syn-opp-01");
  const steps = page.getByRole("navigation", { name: "Ruta de exploración" });
  await steps.getByRole("link", { name: /Costo y factibilidad/ }).click();
  await expect(page.getByRole("tab", { name: "Producción IA" })).toHaveAttribute("aria-selected", "true");
  await steps.getByRole("link", { name: /Validar en español/ }).click();
  await expect(page.getByRole("tab", { name: "Mercado español" })).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/\/opportunities\/syn-opp-01$/);
});

test("se puede añadir una oportunidad al seguimiento y verla con sus notas", async ({ page }) => {
  await page.goto("/opportunities/syn-opp-01");
  const add = page.getByRole("button", { name: "Añadir a seguimiento" });
  const watching = page.getByText("En seguimiento", { exact: true });
  await expect(add.or(watching)).toBeVisible(); // espera a que cargue el estado
  if (await add.isVisible()) await add.click();
  await expect(watching).toBeVisible();
  await page.getByRole("link", { name: "Seguimiento" }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Seguimiento" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 3 })).toContainText("Historia explicada con mapas");
  await expect(page.getByText("Qué cambió desde su última revisión")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alertas" })).toBeVisible();
});

test("Configuración muestra los trabajos programados y la elección de IA por función", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Trabajos programados" })).toBeVisible();
  await expect(page.getByText("Purga de datos caducados")).toBeVisible();
  await expect(page.getByRole("heading", { name: "IA y modelo por función" })).toBeVisible();
});
