# Progreso de implementación

Última actualización: 2026-10-24.

## Hitos

| Hito | Estado | Notas |
|---|---|---|
| **M0 — cimientos y demo sintético** | ✔ Completado (commit `b8762f9`) | Compose, API, worker, migraciones, seed, dashboard, E2E y CI. |
| **M1 — ingesta oficial, cuota y control** | ✔ Completado con límites (sin commit) | Ingesta real probada una vez; ver «Límites» abajo. |
| M2 — nicho/formato, IA, búsqueda en español | — pendiente | |
| M3 — factibilidad, decisiones, comparador completo, export | — pendiente | Export CSV/JSON y watchlist. |
| M4 — analítica avanzada (condicional) | — bloqueado | Requiere `policy_approvals` documentado. |
| M5 — radar continuo | — pendiente | Scheduler, purga automática, alertas. |

## M1: qué se construyó

- **Adaptador oficial** `YouTubeOfficialClient`: `search.list`, `videos.list`, `channels.list`, `playlistItems.list`. Reintentos con backoff, errores tipados y sin clave en los mensajes.
- **Ingesta** por idiomas y ventanas (0–7, 8–30, 31–90 días). Deduplica por ID de YouTube, guarda coincidencias y consultas exactas, y reanuda desde lo ya completado.
- **Cuota por unidades** con día de Pacific Time, corte blando al 90 % y pausa `PAUSED_QUOTA`.
- **Importación JSON/CSV** con validación por fila, errores parciales, idempotencia y confirmación de licencia.
- **Retención**: plazo de 29 días en datos de terceros, purga manual que deja NULL y marca `EXPIRED`.
- **API**: `POST /research-runs` (demo, discovery, purge), `POST …/resume`, `GET /usage`, `POST /imports/provider-file`, `GET /channels/{id}`. Eventos de cada corrida en el detalle.
- **Interfaz**: formulario de búsqueda con costo estimado en Corridas, botón «Reanudar» para corridas pausadas, consumo de cuota en Configuración.

## Verificación de M1

| Comprobación | Resultado |
|---|---|
| Backend: pruebas | **117 pasan** (47 de M0 + 70 nuevas) |
| Backend: ruff y mypy | **sin errores** |
| Frontend: eslint, tsc, vitest (15), build | **sin errores** |
| E2E de M0 | **7 pasan, 1 omitido** |
| Migración 0002 aplicada sobre la base de la demo | **correcta** (migrate, código 0) |
| **Búsqueda real contra YouTube** (1 consulta, 1 página, ventana 31–90 días) | **COMPLETED**: 50 resultados, 102 unidades consumidas, 0 errores |
| Clave en logs y en respuestas de la API | **no aparece** |
| Videos reales guardados | **50**, con procedencia `OFFICIAL`, caducidad a 29 días, idioma y tipo |

Resultado destacado de la prueba real: un video con audio y metadatos en idiomas distintos quedó como `UNKNOWN / CONFLICT`, sin forzar idioma (T04).

## Criterio de aceptación de M1 (§13)

- [x] `YouTubeOfficialProvider` con paginación (T05).
- [x] Importación JSON/CSV con errores por fila y reimportación idempotente.
- [x] Fuente, fecha y TTL en cada registro (`provider`, `observed_at`, `retention_deadline`, `source_data_type`).
- [x] Búsquedas por ventanas e idiomas, con `source_queries` y coincidencias.
- [x] Lista de uploads por `playlistItems` (T06).
- [x] Cuotas separadas por unidades; 429/403 manejados (T19).
- [x] Sin llamadas a APIs en las pruebas (el cliente se prueba con transporte simulado).
- [x] Datos falsos nunca pasan como producción: sin clave no hay búsqueda ni respaldo.
- [ ] Scheduler automático: diferido a M5 (D-29). La búsqueda se lanza a mano.
- [~] Vista de muestra: la pantalla Videos muestra los datos oficiales junto a los sintéticos (ver límites).

## Límites conocidos

- **El banner sigue diciendo «DATOS SINTÉTICOS · DEMO»** aunque ya haya videos reales en la base. Cada fila indica su origen (Videos, columna «Origen»), pero el banner debería cambiar a «DATOS MIXTOS». Pendiente de corregir.
- **Cuota de la especificación corregida** (D-22): `search.list` cuesta 100 unidades, no 1. Confirme la cuota real de su proyecto en Google Cloud Console.
- **La purga no corre sola**: los datos reales caducan a los 29 días y hay que lanzar `kind=purge` a mano hasta M5.
- **Una sola búsqueda real**: la ingesta funciona de punta a punta, pero no se ha probado una búsqueda grande ni la reanudación con cuota real.
- **Sin autenticación**: la API y el worker aceptan peticiones de cualquiera con acceso a `127.0.0.1`.
- **Git**: el commit de M1 no se ha creado (pendiente de su confirmación).

## Siguiente paso

Decidir si M1 se commitea. Después, las dos correcciones de los límites: el banner con datos mixtos y la purga automática diaria. Luego M2 (taxonomía nicho+formato y búsqueda en español).
