# Plan de pruebas

## Cómo se ejecutan

| Capa | Comando | Qué cubre | Estado último |
|---|---|---|---|
| Backend (unitarias + integración) | `docker compose run --rm --no-deps api pytest -q` | Reglas de dominio, compuerta de políticas, migraciones, seed, API, worker | **47 pasan** |
| Backend (lint y tipos) | `docker compose run --rm --no-deps api sh -c "ruff check app tests && ruff format --check app tests && mypy app"` | Estilo y tipos estrictos | **pasa** |
| Frontend (lint y tipos) | `docker compose run --rm --no-deps frontend sh -c "npx eslint . && npx tsc --noEmit"` | ESLint estricto, TypeScript estricto | **pasa** |
| Frontend (unitarias) | `docker compose run --rm --no-deps frontend npx vitest run` | Formato de nulos, selección 2–8, parseo de URL | **10 pasan** |
| Frontend (build) | `docker compose run --rm --no-deps frontend npx vite build` | Build de producción | **pasa** |
| E2E | `docker compose --profile e2e run --rm e2e` | Tres flujos en escritorio y móvil (390 px) y desbordamiento horizontal | **7 pasan, 1 omitido** (ver abajo) |

El caso omitido es «ninguna página produce desplazamiento horizontal» en escritorio: esa comprobación solo corre en el proyecto móvil, a propósito.

## Matriz T01–T25 (§14.1)

Estado: **✔ cubierto en M0** · **◐ parcial** · **— pendiente** (indica el hito).

| ID | Caso | Estado | Dónde / por qué |
|---|---|---|---|
| T01 | Dos fuentes, mismo ID de YouTube | — | M1 (ingesta). `videos.youtube_video_id` es único y los matches van en tabla aparte. |
| T02 | Canal sin suscriptores visibles → NULL | ✔ | `test_nulls_and_zeros_are_kept_distinct`, `test_videos_hidden_subscribers_show_unknown_band`, `subscriber_band` |
| T03 | Video publicado hoy → edad positiva | ✔ | `test_age_for_video_published_now_is_positive_and_bounded` |
| T04 | Idioma de título ≠ audio | ◐ | Dato en conflicto (`UNKNOWN`/`CONFLICT`) verificado; la detección real llega en M1–M2. |
| T05 | Paginación de `search.list` | — | M1 (sin `search.list` en M0). |
| T06 | Uploads playlist en lugar de `search.list` | — | M1. |
| T07 | Viral aislado → no replicado | ◐ | El dato `SINGLE_OUTLIER` existe; la regla de replicación es M2. |
| T08 | Mismo formato, varios idiomas | — | M2. |
| T09 | Mismo formato, nicho distinto → dos oportunidades | ✔ | Fixture: `syn-opp-02` y `syn-opp-04` comparten formato y son oportunidades distintas (clave única nicho+formato+idioma+tipo). |
| T10 | Ningún competidor ES → `UNKNOWN` | — | M2 (búsqueda ES). |
| T11 | Búsquedas ES sin demanda → `DEMAND_UNPROVEN` | ◐ | Dato existente (`syn-opp-03`); la regla que lo produce es M2. |
| T12 | Canal espejo multilingüe | — | M2. |
| T13 | IA inventa URL o score | — | M2 (validación de salida IA). |
| T14 | Prompt injection en título | — | M2. |
| T15 | Costo TTS ausente → NULL | ◐ | `syn-opp-07` tiene costos NULL; el desglose de TTS es M3. |
| T16 | Datos expirados → UI dice expirado | ◐ | Evidencia `EXPIRED` visible en ficha (`test_detail_includes_expired_evidence_flagged`); purga es M5. |
| T17 | Score bloqueado en restricted | ✔ | `test_scores_endpoint_is_forbidden_in_restricted_mode`, `test_env_flag_alone_does_not_unlock_restricted_capability`, E2E de Resumen |
| T18 | Autorización de derived metrics expira | — | M4. |
| T19 | 403 de cuota → pausa proveedor | — | M1. |
| T20 | CSV con fórmula `=…` | — | M3 (exportación). |
| T21 | Corrida reintentada sin duplicados | ✔ | `test_worker_completes_demo_run_once`, `test_repeated_requests_create_separate_runs_without_duplicate_work`, `test_seed_is_idempotent`, `test_stale_running_task_is_recovered` |
| T22 | Demo activo → banner y ningún origen real | ✔ | `test_every_record_is_labelled_synthetic`, `test_config_public_is_demo_and_restricted`, banner en E2E |
| T23 | Comparación de 8 ítems | ✔ | `test_compare_eight_items_keeps_nulls_and_restrictions` (API). La UI con 8 se cubre a mano; E2E cubre 4. |
| T24 | Sin permisos → no puede iniciar acciones ni ver secretos | ◐ | `test_providers_never_expose_secret_values`. Autenticación no implementada (ver D-10). |
| T25 | Valor observado antes de cambio de política | — | M4/M5. |

## Pruebas no funcionales cubiertas

- **Secretos:** las claves se leen como `SecretStr`; los logs redactan campos sensibles (`test_log_redaction_hides_secret_like_keys`).
- **Inyección SQL:** los parámetros de búsqueda son parámetros ligados; un texto con metacaracteres se trata como texto (`test_sql_metacharacters_in_search_are_plain_text`). El orden se valida contra una lista blanca (`test_invalid_sort_is_problem_json`).
- **Migraciones reproducibles:** la base de pruebas se recrea y se compara con los modelos (`test_migrations_match_models`).
- **Accesibilidad y responsive:** E2E comprueba que ninguna página principal tiene desplazamiento horizontal en 390 px. Contraste y teclado no se han medido automáticamente.

## Pendiente de verificar

- Playwright en el navegador real del usuario: solo se probó en el contenedor oficial de Playwright.
- CI en GitHub Actions: el archivo `.github/workflows/ci.yml` no se ha ejecutado en GitHub.
- Restauración de copias de seguridad: pertenece a M5.
