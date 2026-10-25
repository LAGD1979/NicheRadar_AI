# Plan de pruebas

## Cómo se ejecutan

| Capa | Comando | Qué cubre | Último resultado |
|---|---|---|---|
| Backend (unitarias + integración) | `docker compose run --rm --no-deps api pytest -q` | Dominio, cliente de YouTube (simulado), ingesta, cuota, importación, purga, API, worker | **117 pasan** |
| Backend (lint y tipos) | `docker compose run --rm --no-deps api sh -c "ruff check app tests && ruff format --check app tests && mypy app"` | Estilo y tipos estrictos | **pasa** |
| Frontend (lint, tipos) | `docker compose run --rm --no-deps frontend sh -c "npx eslint . && npx tsc --noEmit"` | ESLint estricto, TypeScript estricto | **pasa** |
| Frontend (unitarias) | `docker compose run --rm --no-deps frontend npx vitest run` | Formato de nulos, selección 2–8, URL, formulario de búsqueda | **15 pasan** |
| E2E | `docker compose --profile e2e run --rm e2e` | Flujos de M0 en escritorio y móvil (390 px) | **7 pasan, 1 omitido** (solo aplica al móvil) |

Ninguna prueba automática llama a YouTube: el fixture anula `YOUTUBE_API_KEY` y el cliente se prueba con un transporte simulado (`httpx.MockTransport`).

**Prueba real (fuera de la suite):** una búsqueda contra la API oficial con una consulta y una página (ver `IMPLEMENTATION_PROGRESS.md`).

## Matriz T01–T25 (§14.1)

Estado: **✔ cubierto** · **◐ parcial** · **— pendiente** (indica el hito).

| ID | Caso | Estado | Dónde / por qué |
|---|---|---|---|
| T01 | Dos fuentes, mismo ID de YouTube | ✔ | `test_same_video_from_two_queries_is_one_row_with_two_matches` |
| T02 | Canal sin suscriptores visibles → NULL | ✔ | `test_hidden_subscribers_are_null_and_zero_stays_zero`, `test_hidden_subscribers_are_null_and_zero_is_kept`, `test_counts_never_turn_missing_into_zero` |
| T03 | Video publicado hoy → edad positiva | ✔ | `test_age_for_video_published_now_is_positive_and_bounded` (M0) |
| T04 | Idioma de título ≠ audio | ✔ | `test_language_conflict_from_api_is_stored_unknown`, `test_language_conflict_is_unknown_not_forced`. El idioma por título no existe aún (D-29). |
| T05 | `search.list` con página siguiente | ✔ | `test_pagination_uses_second_page_within_page_budget`, `test_search_sends_window_and_language_and_returns_next_page` |
| T06 | Uploads por `playlistItems`, no `search` | ✔ | `test_uploads_are_loaded_by_playlist_not_by_search`, `test_uploads_use_playlist_items_not_search` |
| T07 | Viral aislado → no replicado | — | M2 (regla de replicación). |
| T08 | Mismo formato, varios idiomas | — | M2. |
| T09 | Mismo formato, nicho distinto | ✔ | Fixture M0 (`syn-opp-02`, `syn-opp-04`). |
| T10 | Ningún competidor ES → `UNKNOWN` | — | M2 (búsqueda ES). |
| T11 | Búsquedas ES sin demanda | ◐ | Dato existente (`syn-opp-03`); la regla es M2. |
| T12 | Canal espejo multilingüe | — | M2. |
| T13 | IA inventa URL o score | — | M2. |
| T14 | Prompt injection en título | — | M2. |
| T15 | Costo TTS ausente → NULL | ◐ | Costos NULL en el fixture; el desglose es M3. |
| T16 | Datos caducados → UI dice caducado | ✔ | `test_purge_expires_old_third_party_data_without_zeros`, `test_purge_leaves_fresh_and_authorized_data_alone`, `test_purge_is_idempotent`. La UI muestra «Caducada». |
| T17 | Score bloqueado en restricted | ✔ | `test_env_flag_alone_does_not_unlock_restricted_capability`, `test_scores_endpoint_is_forbidden_in_restricted_mode` |
| T18 | Autorización de métricas derivadas expira | — | M4. |
| T19 | 403 de cuota → pausa, continúa donde puede | ✔ | `test_quota_403_maps_to_paused_quota_and_never_leaks_key`, `test_quota_budget_pauses_and_keeps_progress`, `test_quota_pause_then_resume_completes_remaining_work` |
| T20 | CSV con fórmula `=…` | ◐ | La importación guarda la fórmula como texto (`test_csv_with_formula_text_is_stored_as_plain_text`). La neutralización en la **exportación** es M3. |
| T21 | Corrida reintentada sin duplicados | ✔ | `test_reingesting_the_same_results_creates_no_duplicates`, `test_reimporting_same_key_is_idempotent`, `test_worker_completes_demo_run_once`, `test_stale_running_task_is_recovered` |
| T22 | Demo activo → banner y sin origen real | ◐ | Los datos sintéticos siguen rotulados. Tras la prueba real aparecen videos `OFFICIAL` en la misma base; el banner todavía no distingue datos mixtos (ver progreso). |
| T23 | Comparación de 8 ítems | ✔ | `test_compare_eight_items_keeps_nulls_and_restrictions` (API) |
| T24 | Sin permisos → no inicia acciones ni ve secretos | ◐ | Sin clave, la búsqueda responde 409 (`test_discovery_without_key_is_refused_before_queueing`); los endpoints no exponen claves (`test_providers_never_expose_secret_values`). Sin autenticación todavía. |
| T25 | Valor observado antes de cambio de política | — | M4/M5. |

## Pruebas no funcionales cubiertas

- **Secretos:** la clave no aparece en logs ni en respuestas. Comprobado con la clave real: `clave en logs: False`, `clave en respuestas de la API: False`.
- **Errores de proveedor:** 429/5xx con reintento y backoff; 400 sin reintento; timeouts; ningún mensaje contiene URL ni clave.
- **Inyección SQL:** búsquedas con metacaracteres se tratan como texto; orden validado contra lista blanca.
- **Migraciones:** la base de pruebas se recrea y se compara con los modelos (`test_migrations_match_models`).
- **Zona horaria de cuota:** la frontera de medianoche Pacific Time (`test_quota_day_starts_at_pacific_midnight`).

## Pendiente de verificar

- Una búsqueda real repetida y la purga de datos reales en un día distinto (solo se ejecutó una vez).
- Playwright en el navegador del usuario (solo en el contenedor oficial).
- CI en GitHub Actions (no ejecutado remotamente).
