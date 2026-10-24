# Decisiones e interpretaciones

Registro de decisiones tomadas durante M0. Cada una indica qué se decidió, por qué y dónde se aplica.

## D-01 · Ubicación del repositorio
El proyecto vive en `…\NicheRadar_AI_Claude_Code\NicheRadar_AI`, dentro de Dropbox, por elección del usuario. La carpeta padre conserva los documentos originales. **Riesgo conocido:** Dropbox puede bloquear archivos mientras Docker o Vite escriben; `node_modules` y `dist` se evitan con volúmenes nombrados y `.gitignore`. Si aparecen bloqueos, mover el repositorio fuera de Dropbox.

## D-02 · Puerto de PostgreSQL en el host: 15432
En este equipo, `127.0.0.1:5432` devolvía «access forbidden» al publicarse en Docker. El puerto es configurable con `DB_HOST_PORT`. Dentro de la red de Compose la base sigue en 5432.

## D-03 · Prefijos de rutas
Los endpoints de datos viven bajo `/api/v1` (según §7 de la especificación). Los de salud viven en `/health/*` sin prefijo (según CLAUDE.md y §7). `/config/public` y demás rutas de §7 se sirven bajo `/api/v1`.

## D-04 · Duplicidad en la especificación
ESPECIFICACION_NICHERADAR_AI.md numera dos veces §8 a §13 (líneas ~501–1553). Para M0 se tomaron como fuente: §12 «Estructura», §13 «Entrega por fases» (hito M0), §14 «Pruebas», §15 «Despliegue» y §16 «Definition of Done». La etapa 0 de §12 (línea 769) se usó como detalle de arranque. Esta decisión debe confirmarse con el autor del documento.

## D-05 · Nombre de la clave de YouTube
Se usa `YOUTUBE_API_KEY` (como §14 y el `.env.example` original). §15.1 dice `YT_API_KEY`; se considera una errata.

## D-06 · Navegación del dashboard
CLAUDE.md pide las vistas Resumen, Videos, Oportunidades, Detalle, Comparador, Corridas, Seguimiento y Configuración. §8.1 pide ocho rutas distintas. Se implementaron las de CLAUDE.md, con rutas: `/`, `/opportunities`, `/opportunities/:id`, `/videos`, `/compare`, `/runs`, `/settings`. **Seguimiento (watchlist) queda para M3.** Descubrimiento internacional y Mercado español se muestran dentro de la ficha y de Resumen en M0.

## D-07 · Worker mínimo, no un stub
El criterio de M0 exige un servicio `worker`. Para no crear un proceso que finja trabajar, el worker toma tareas de `run_tasks` con `FOR UPDATE SKIP LOCKED`, recupera tareas con arrendamiento vencido, reintenta hasta 3 veces y registra fallos. Solo ejecuta `demo_research`, que lee el dataset sintético y no hace red. Es un adelanto acotado de la cola de M5.

## D-08 · Dataset sintético
`backend/app/demo/fixtures/synthetic_v1.json`: 5 nichos, 4 formatos, 10 canales (8 pequeños, 2 de control), 20 videos y 8 oportunidades. Todos los nombres son ficticios («Canal Sintético Alfa», etc.) y todos los registros llevan `source_data_type=SYNTHETIC`. Incluye: una oportunidad sin evaluación, una con evaluación parcial, una evidencia caducada, un video con conflicto de idioma, un Short de 100 s clasificado como `UNKNOWN`, un largo de 12 min y un canal con suscriptores `NULL` y otro con cero real.

## D-09 · Seed idempotente por ID estable
Cada registro tiene ID fijo; el seed usa `session.merge` (upsert). Ejecutarlo dos veces produce los mismos conteos. El fixture no se muta en memoria.

## D-10 · Compuerta de políticas
`compliance_service.decide()` devuelve `RESTRICTED` para todas las capacidades condicionadas. En M0 `COMPLIANCE_MODE` solo acepta `restricted`, y `APP_ENV=production` se rechaza porque no hay autenticación. `ADVANCED_ANALYTICS_ENABLED=true` no cambia el resultado (probado).

## D-11 · Migraciones y servicio `migrate`
Un servicio de un solo uso ejecuta `alembic upgrade head` y el seed. `api` y `worker` esperan a que termine con código 0. La migración inicial se escribió a mano; una prueba compara el esquema migrado con los modelos (`compare_metadata`).

## D-12 · Base de pruebas recreada por sesión
Las pruebas de integración usan `nicheradar_test`, que se borra y recrea al inicio de cada sesión. Así cada ejecución prueba las migraciones desde cero.

## D-13 · Dependencias fijadas, sin uv
Backend: `requirements.txt` y `requirements-dev.txt` con versiones exactas (pip, no uv, porque el host no tiene uv y todo corre en la imagen). Frontend: `package.json` con versiones exactas y `package-lock.json` generado. §4.1 pedía `uv` con lockfile; se toma como preferencia, no como requisito.

## D-14 · Estilos sin Tailwind
Se usa CSS propio con variables y modo oscuro (`prefers-color-scheme` y `data-theme`). CLAUDE.md pide evitar frameworks que no aporten valor; con cuatro pantallas Tailwind añadía una capa de build sin beneficio claro. Si el diseño crece, se reevalúa.

## D-15 · Tipos del frontend escritos a mano
`frontend/src/types.ts` refleja los esquemas de Pydantic. §14.3 pide un cliente generado desde OpenAPI; se pospone a M3, cuando el contrato esté estable. El riesgo de divergencia lo cubren las pruebas E2E.

## D-16 · Comparación por POST
`POST /api/v1/compare` recibe la lista de IDs en el cuerpo (2 a 8, sin repetidos), en lugar de un `GET` con query, para no depender de la longitud de la URL. La selección del radar se conserva en la URL del comparador (`?ids=`).

## D-17 · Sin ganador en el comparador
La celda de saturación baja no se destaca como ganadora cuando la demanda no está demostrada (§8.9). M0 no resalta ninguna celda.

## D-18 · Estados vacíos y nulos
`NULL` se muestra como «Sin dato», nunca como 0. Un campo restringido se muestra como «No habilitado» con su motivo. Un cero real (p. ej. 0 suscriptores) se muestra como 0.

## D-19 · Puerto de la API y el frontend
Por defecto `8000` y `5173`, configurables con `API_HOST_PORT` y `FRONTEND_HOST_PORT`. El proxy de Vite reenvía `/api` a la API, así que el navegador no necesita CORS.

## D-20 · Alcance de M0 frente a T01–T25
M0 cubre los casos T02, T03, T04 (parcial, a nivel de dato), T17, T21, T22, T23 y T24 (parcial). Los demás quedan explícitos en [docs/TEST_PLAN.md](TEST_PLAN.md) como pendientes del hito que los necesita.

## D-21 · Preflight de entorno
`scripts/check_environment.py` del plan original no se implementó: Docker Compose ya se verificó a mano y el stack arranca. Queda para cuando haya un entorno nuevo que validar.
