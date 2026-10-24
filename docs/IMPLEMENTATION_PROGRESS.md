# Progreso de implementación

Última actualización: 2026-10-24.

## Hitos

| Hito | Estado | Notas |
|---|---|---|
| **M0 — cimientos y demo sintético** | ✔ **Completado** (con los límites indicados abajo) | Compose, API, worker, migraciones, seed, dashboard, E2E y CI listos. |
| M1 — ingesta oficial YouTube, cuotas | — pendiente | Requiere clave de YouTube autorizada. |
| M2 — nicho/formato, IA, búsqueda en español | — pendiente | |
| M3 — factibilidad, decisiones, comparador completo, export | — pendiente | Export CSV/JSON y watchlist van aquí. |
| M4 — analítica avanzada (condicional) | — bloqueado | Requiere `policy_approvals` documentado. |
| M5 — radar continuo | — pendiente | Scheduler semanal, purga, alertas. |

## Verificación de M0 (último resultado, código actual)

| Comprobación | Comando | Resultado |
|---|---|---|
| Backend: pruebas | `docker compose run --rm --no-deps api pytest -q` | **47 pasan** |
| Backend: lint y tipos | `ruff check`, `ruff format --check`, `mypy app` | **sin errores** |
| Frontend: lint | `npx eslint .` | **sin errores** |
| Frontend: tipos | `npx tsc --noEmit` | **sin errores** |
| Frontend: unitarias | `npx vitest run` | **10 pasan** |
| Frontend: build | `npx vite build` | **correcto** |
| E2E (Playwright, contenedor oficial) | `docker compose --profile e2e run --rm e2e` | **7 pasan, 1 omitido** (desktop-only de la comprobación móvil) |
| Arranque desde cero | `docker compose down -v` y `up -d --build` | **`/health/ready` = ready** |
| Migraciones reproducibles | `compare_metadata` en pruebas; `up` desde volumen vacío | **sin diferencias** |
| Seed idempotente | `migrate` ejecutado dos veces | **8 oportunidades en ambas ejecuciones** |
| Documentación API | `GET /docs` | **200** |

## Criterio de aceptación de M0 (§13)

- [x] `docker compose up --build` levanta interfaz, API, worker, base y migraciones.
- [x] `GET /health/ready` responde 200 y la versión de migración coincide con el código.
- [x] Migraciones reproducibles desde cero.
- [x] Demo carga sin claves de API.
- [x] Sin secretos en el repositorio (`.env` ignorado; el `.env.example` no tiene valores).
- [x] Dataset sintético rotulado (banner y `SYNTHETIC` en todos los registros).
- [x] Radar con filtros, ficha con pestañas y comparador (4 en E2E; 8 en API).
- [x] Nulos como «Sin dato»; restringidos como «No habilitado»; sin ganador en el comparador.
- [x] Sin desplazamiento horizontal en 390 px en las páginas principales.

## Limitaciones conocidas de M0

- **Sin ingesta real.** Todos los datos son sintéticos (D-08).
- **Sin exportación CSV/JSON** (T20 pendiente, M3).
- **Sin autenticación.** `APP_ENV=production` se rechaza (D-10).
- **Watchlist (Seguimiento) no implementada** (D-06).
- **Cliente de API escrito a mano**, no generado desde OpenAPI (D-15).
- **Pruebas en navegador:** Playwright se ejecutó en el contenedor oficial, no en el navegador del usuario.
- **CI no ejecutado en GitHub.** El workflow se escribió y su sintaxis no se ha validado remotamente.
- **Git:** el repositorio tiene `git init` pero no hay commits. No se ha creado ningún commit.

## Bloqueos y decisiones de entorno

- **Puerto 5432 bloqueado** por Windows al publicarse en Docker; se usa 15432 (D-02).
- **Dropbox:** el repositorio está en una carpeta sincronizada (D-01). No se han observado bloqueos durante M0, pero es un riesgo a vigilar.
- **Especificación con secciones duplicadas** (D-04): pendiente de confirmar con el autor.

## Siguiente paso

Arrancar M1 cuando haya una clave de YouTube Data API autorizada (o usar el modo mock). Primer paso concreto: adaptador `YouTubeOfficialProvider` con límites de cuota y pruebas sin red, y migración de `source_queries`, `discovery_matches` y `provider_usage`.
