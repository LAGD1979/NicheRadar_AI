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

---

## M1 — ingesta oficial de YouTube

### D-22 · La cuota se mide en unidades, no en llamadas (corrige la especificación)
§5.2 de la especificación dice «100 llamadas diarias a `search.list` (costo 1 cada una)». Eso no coincide con la documentación oficial: `search.list` cuesta **100 unidades** y el pool diario por defecto es **10 000 unidades compartidas** por todos los métodos (`videos.list`, `channels.list`, `playlistItems.list` cuestan 1 unidad cada uno). Fuentes: [Determine quota cost](https://developers.google.com/youtube/v3/determine_quota_cost) y [YouTube Data API overview](https://developers.google.com/youtube/v3/getting-started).

Consecuencia: el límite se controla en unidades (`YOUTUBE_DAILY_UNITS_LIMIT=10000`, corte blando al 90 % = 9 000). Con 80 búsquedas de 100 unidades ya se consumen 8 000, así que la cuota restante para detalles es pequeña. **Conviene confirmar la cuota real de su proyecto en Google Cloud Console** antes de programar búsquedas grandes.

### D-23 · El día de cuota es el de Pacific Time
La cuota se reinicia a medianoche de Pacific Time, no UTC (D-22 y documentación oficial). `quota_service.quota_day_start` lo calcula; hay pruebas de la frontera.

### D-24 · Clave de YouTube: solo por entorno
`YOUTUBE_API_KEY` llega a `api` y `worker` desde la variable de entorno del host o desde `.env` (Compose la interpola). Nunca se escribe en el repositorio ni en respuestas, y `httpx` se silencia a `WARNING` para que no registre la URL con la clave. Las pruebas la anulan explícitamente (`conftest.py`), así que nunca salen a la red aunque la clave exista en el equipo.

### D-25 · Sin clave, no hay búsqueda y no hay datos de respaldo
Sin clave, `POST /research-runs` con `kind=discovery` responde 409 `PROVIDER_NOT_CONFIGURED`. No se inventan datos ni se marca como éxito. Los datos sintéticos siguen siendo solo DEMO.

### D-26 · Pausa y reanudación por cuota
Un 403 `quotaExceeded` o el corte local deja la corrida en `PAUSED_QUOTA`, con el progreso (consultas completadas) guardado en la tarea. `POST /research-runs/{id}/resume` la reanuda y solo ejecuta lo pendiente. Un 403 de credencial (`forbidden`, `keyInvalid`) no pausa: falla la corrida, porque requiere acción humana (§9.3).

### D-27 · Retención de datos de terceros: 29 días
Todo lo que viene de la API o de una importación se guarda con `owner_authorized=false` y `retention_deadline = observado + 29 días` (§5.5). La purga (`kind=purge`) deja los valores en NULL, marca `EXPIRED` y cambia el título a «[Dato caducado]». **La purga no corre sola**: se lanza manualmente hasta M5.

### D-28 · Importación JSON/CSV con confirmación de licencia
`POST /imports/provider-file` exige `license_confirmed=true`. Valida fila por fila, acepta las válidas, devuelve los errores de las demás (fila, campo, motivo) y es idempotente por `(proveedor, idempotency_key)`. Los valores como `=HYPERLINK(...)` se guardan como texto; la exportación los neutralizará en M3 (T20).

### D-29 · Lo que M1 no implementa todavía
- **Observations** (tabla de la especificación §6): la procedencia y la retención viven en las columnas de `videos` y `channels`. La tabla completa se evaluará en M2.
- **Expansión por canal** (`playlistItems` para uploads): el servicio existe y está probado (T06), pero no hay ruta HTTP para dispararlo.
- **Scheduler automático**: todo es manual (D-26). Lo automático llega en M5.
- **Detección de idioma por el título**: solo se usan `defaultAudioLanguage` y `defaultLanguage`. Sin ellos el idioma queda `UNKNOWN`.

---

## M2 — mercado español y planes de búsqueda

### D-30 · Una oportunidad = nicho + formato + idioma + tipo
`ensure_opportunity` crea o reutiliza la oportunidad por esa combinación (restricción única). Un mismo formato en otro nicho es otra oportunidad (T09). Anotar un video crea la oportunidad si no existe. El tipo sale del video: si es `UNKNOWN` o `LIVE`, la anotación se rechaza (`VIDEO_TYPE_UNCLEAR`), para no mezclar largos y Shorts.

### D-31 · La IA está desactivada hasta que haya clave, modelo y proveedor
`AI_PROVIDER=none` por defecto y `AI_MODEL` vacío. Sin ellos, `POST …/search-plans/generate` responde 409 `AI_NOT_CONFIGURED`. El cliente de Anthropic (`app/providers/ai.py`) está implementado según el contrato de la API de Mensajes, **pero no se ha ejecutado contra la API real**: no hay clave de Anthropic configurada. Los tests usan un doble de prueba.

### D-32 · La IA solo propone; el dominio valida
La respuesta se parsea con Pydantic. Se rechaza si no es JSON (`INVALID_JSON`), si no cumple el esquema (`INVALID_PLAN`), si cita un `source_id` que no existe en la evidencia (`INVALID_EVIDENCE_REF`) o si incluye una URL (T13). En esos casos el plan queda `NEEDS_REVIEW` sin datos de plan. Los títulos entran en el prompt dentro de un JSON como datos, con instrucciones de no obedecerlos (T14). Prompt versionado: `P2-1`.

### D-33 · Planes versionados; un plan aprobado no se edita
Un plan aprobado queda bloqueado (`PLAN_LOCKED`). Aprobar otro plan de la misma oportunidad marca el anterior como `SUPERSEDED`. Un plan escrito por una persona (`origin=HUMAN`) se valida con el mismo esquema que el de la IA.

### D-34 · Competidor exacto solo con revisión humana
Todas las coincidencias nacen `UNREVIEWED`. Solo cuentan como `EXACT` cuando una persona lo marca (`PATCH /matches/{id}`). Un video cuenta como español solo si su idioma verificado es `es`; uno con audio en otro idioma no cuenta, aunque aparezca en la búsqueda.

### D-35 · Reglas de saturación y decisión (domain/spanish_market.py)
- Cobertura mínima: 6 consultas y 2 variantes. Con menos, la saturación es `UNKNOWN` (`ES_QUERY_COVERAGE_LOW`).
- Sin ningún video verificado en español: `UNKNOWN`. Sin ninguna coincidencia revisada: `UNKNOWN` (`ES_MATCH_NOT_REVIEWED`). Nunca `LOW` sin revisión (T10).
- Con revisión: `LOW` si hay 0 exactos, `MEDIUM` si hay 1–4, `HIGH` si hay 5 o más.
- Demanda: 0 señales independientes = `UNPROVEN`; 1 = `INDICATIVE`; 2 o más = `OBSERVED`.
- Decisión: primero se comprueba la cobertura, luego la demanda (T11: sin demanda, `DEMAND_UNPROVEN` aunque haya búsquedas completas), luego la saturación.
- La confianza nunca sube por ausencia de resultados.

**Limitación importante:** M2 no tiene fuentes de señales de demanda. Google Trends está desactivado y no hay búsquedas con licencia. Por tanto, hoy **ninguna oportunidad puede pasar de `DEMAND_UNPROVEN`**, y `GAP_CONFIRMED` / `POTENTIAL_GAP` no se alcanzan. Es lo correcto según la especificación (§3.6), pero conviene saberlo antes de interpretar el radar.

### D-36 · Evaluación append-only
Cada validación o revisión añade una versión nueva de la evaluación. Las versiones anteriores no se modifican. La versión vigente es la de mayor número. Las secciones internacional y de factibilidad se copian de la versión anterior; la de español se recalcula.

### D-37 · Cobertura calculada sobre todas las búsquedas de la oportunidad
`source_queries` y `discovery_matches` tienen `opportunity_id`. La cobertura se recalcula sobre todas las búsquedas de la oportunidad, no solo sobre la última corrida. Así una revisión posterior actualiza el estado sin repetir búsquedas.

### D-38 · Resultados de búsqueda como muestra, no como censo
Los contadores de cobertura son lo que devolvió YouTube para esas consultas. No representan el total de competidores (§3.6).

---

## M3 — costos, factibilidad, recomendación y exportación

### D-39 · Costos sin precios inventados
Cada línea de costo tiene cantidad y un precio por escenario (bajo, base, alto), escrito por una persona. Si falta un precio en un escenario, el total de ese escenario es NULL y se lista la línea faltante (T15). Un precio vacío nunca se convierte en 0. Las cantidades 0 también necesitan precio.

### D-40 · Modelo de costo versionado
`cost_models` es append-only. Cada guardado crea una versión nueva y actualiza los costos de la evaluación vigente (`usd_per_video_scenarios`), marcados como estimación.

### D-41 · Factibilidad con motivo obligatorio
El faceless y el riesgo de derechos los valora una persona (`assessed_by`). El motivo del faceless tiene al menos 20 caracteres. Un riesgo de derechos medio o alto exige una explicación de 20 caracteres o más. Nada se deduce de una miniatura o un título (§0).

### D-42 · Compuertas y recomendación deterministas
`domain/decision.py` calcula la recomendación y las compuertas. Las compuertas son `INSUFFICIENT_EVIDENCE`, `DEMAND_UNPROVEN`, `HIGH_COPYRIGHT_RISK`, `RIGHTS_NOT_ASSESSED`, `FACELESS_NOT_ASSESSED` y `COMPLEXITY_NOT_ASSESSED`. Orden de las reglas:
- Riesgo alto de derechos → `REJECT`.
- Saturación española «saturada» → `WATCHLIST`.
- Replicación internacional débil o ausente → `MORE_RESEARCH`.
- Cobertura insuficiente → `MORE_RESEARCH`.
- Demanda no demostrada → `VALIDATE_DEMAND_PILOT` (§3.6: piloto de validación, no lanzamiento).
- Cualquier otra compuerta → `MORE_RESEARCH`.
- `READY_FOR_PILOT` solo si no hay compuertas, la entrada es «posible brecha», la demanda es observada o indicativa, la confianza es media o alta, el faceless es confirmado o probable, la complejidad es 3 o menos y el riesgo de derechos es bajo o medio.

### D-43 · La recomendación se recalcula en cada versión
`evaluation_service.append_evaluation` recalcula recomendación y compuertas con la versión resultante. La validación en español (M2) también usa este servicio, así que una revisión de competidor actualiza la recomendación.

### D-44 · Exportación con neutralización de fórmulas
`GET /exports/opportunities.csv|json` exporta lo que se ve con los filtros activos (hasta 1000 filas). Las celdas que empiezan por `=`, `+`, `-`, `@`, tabulador o retorno se prefijan con `'` (T20). Cada fila y cada JSON llevan la advertencia de caducidad de 29 días.

### D-45 · Datos de demo con recomendación alta
El fixture sintético `syn-opp-01` declara demanda indicativa y confianza media. Con factibilidad FACELESS_LIKELY, complejidad 2 y riesgo bajo, su recomendación pasa a `READY_FOR_PILOT`. **Es un dato de demo rotulado como sintético, no una señal real.** Ninguna oportunidad real puede llegar ahí sin una fuente de demanda.

### D-46 · Recomendaciones del fixture hasta que haya una evaluación nueva
Las oportunidades sintéticas muestran la recomendación del fixture hasta que se registra una evaluación nueva. Ahí se recalcula con las reglas de arriba.

---

## Proveedor de IA: OpenAI además de Anthropic

### D-47 · Dos adaptadores con la misma interfaz
`AI_PROVIDER=anthropic` o `AI_PROVIDER=openai`, con `AI_MODEL` y la clave correspondiente. El adaptador de OpenAI usa Chat Completions con `response_format: json_object`, `temperature: 0` y `max_completion_tokens`. Ambos comparten reintentos (3 intentos ante 429, 5xx y timeouts; sin reintento ante 400) y no muestran la clave en los errores.

**Actualización 2026-10-25:** OpenAI se probó en vivo (ver D-55). Anthropic se probó también (ver D-56). Los modelos de razonamiento pueden rechazar `temperature: 0`; en ese caso la llamada devuelve error y habrá que ajustar el adaptador.

**Sin pausa entre reintentos de IA**: a diferencia de YouTube, los reintentos de IA no esperan (`2^n` segundos). Conviene añadir espera antes de usarlo en lote.

### D-55 · Prueba en vivo del adaptador de OpenAI (2026-10-25)
Con `AI_PROVIDER=openai` y `AI_MODEL=gpt-4.1-mini`, `POST /opportunities/syn-opp-01/search-plans/generate` terminó en unos 5 segundos y dejó un plan `PENDING_REVIEW` válido: tres grupos (`ALL_ES`, `LATAM`, `ES`), exclusiones, notas de localización y solo `source_id` existentes. La clave no aparece en los logs de `api` ni `worker`.

- **Modelo:** se eligió un modelo de chat clásico porque el adaptador envía `temperature: 0`, que los modelos de razonamiento pueden rechazar. Los modelos disponibles en la cuenta se consultaron con `GET /v1/models`.
- **Compose:** `docker-compose.yml` pasa ahora `OPENAI_API_KEY` y `ANTHROPIC_API_KEY` desde el entorno del host a `api` y `worker`, como ya hacía con la de YouTube. Antes la clave no llegaba a los contenedores.
- **Configuración local:** `AI_PROVIDER` y `AI_MODEL` viven en el `.env` (no versionado).
- **Sin probar:** calidad de las frases (un plan de IA siempre lo aprueba una persona), reintentos ante 429/5xx, modelos de razonamiento, y Anthropic.

### D-56 · Prueba en vivo del adaptador de Anthropic y corrección de `temperature` (2026-10-25)
La primera llamada con `claude-haiku-5-5` falló con HTTP 400. Una llamada directa a la API mostró el motivo: «`temperature` is deprecated for this model». El adaptador la enviaba siempre en 0. Se **quitó `temperature` de la petición a Anthropic** (`providers/ai.py`) y se añadió `tests/unit/test_anthropic_client.py`, que fija que no se envía. Con el cambio, `POST …/search-plans/generate` creó un plan `PENDING_REVIEW` válido de tres grupos para `syn-opp-02` y `syn-opp-03`.

- **Consecuencia:** sin `temperature`, la salida de Anthropic no es determinista. Es aceptable porque el plan se valida con esquema y lo aprueba una persona (D-32).
- **Modelo:** `claude-haiku-5-5`, elegido de `GET /v1/models` por ser el más económico de la lista.
- **Clave:** el responsable guardó la clave en `CLAUDE_API_KEY`. Compose la acepta como respaldo de `ANTHROPIC_API_KEY`. No aparece en los logs de `api` ni `worker`.
- **Config local:** el `.env` (no versionado) deja `AI_PROVIDER=anthropic` y `AI_MODEL=claude-haiku-5-5`.
- **Pendiente:** el adaptador de OpenAI sigue enviando `temperature: 0`; falla con modelos que no lo admitan (D-47).

---

## vidIQ por MCP

### D-57 · Adaptador de vidIQ (2026-10-25)
vidIQ ofrece un servidor MCP remoto (`https://mcp.vidiq.com/mcp`) con claves de API de **solo lectura** para clientes que no pueden iniciar sesión. `providers/vidiq_mcp.py` es un cliente MCP (JSON-RPC sobre HTTP) con `Authorization: Bearer`; lee los datos estructurados de `_meta.widgetData`, no el texto en markdown. Solo implementa `vidiq_outliers` y `vidiq_balance` (gratis).

- **Compuerta:** la corrida `kind=vidiq` exige la capacidad `vidiq_api` abierta (las tres condiciones de D-48), en la API (403) y otra vez en el worker. Sin `VIDIQ_API_KEY`, 409.
- **Créditos:** cada consulta cuesta 5 créditos del plan. Hay un tope diario local (`VIDIQ_DAILY_CREDIT_LIMIT`, 200) y un tope por corrida (`max_calls`). Agotar el tope pausa la corrida (`PAUSED_QUOTA`) y se reanuda como la de YouTube. El saldo real del plan no se consulta antes de cada llamada.
- **Datos:** se guardan como `PROVIDER`, `owner_authorized=false` y caducan a **29 días**, igual que YouTube. Las métricas de vidIQ (breakout, vistas por hora, categorías de formato) van en `videos.provider_metrics` bajo la clave `vidiq`, con `run_id` y `observed_at`; la purga las borra con el video (migración 0005).
- **Procedencia:** si el video ya existe con otra procedencia, no se sobrescribe; solo se añade la clave `vidiq`.
- **Idioma:** el filtro de idioma del título de vidIQ **no** es idioma verificado; los videos quedan `UNKNOWN`.
- **Sin sesgo de tema:** una consulta puede ir sin palabra clave, solo con filtros de idioma, tamaño de canal y vistas, o con una categoría de formato.
- **Registros inválidos:** se descartan, se cuentan y la corrida queda `PARTIAL` con `RECORDS_SKIPPED`.
- **Términos de vidIQ (revisados por el responsable, 2026-10-25):** según su lectura, las prohibiciones de extracción automatizada no aplican al servidor MCP usado conforme a su documentación; los datos de plataformas de terceros obtenidos por MCP siguen sujetos a los términos y límites de almacenamiento de la plataforma de origen (YouTube), y vidIQ no fija un plazo propio de retención. El asistente no leyó los Términos: es una conclusión del responsable. Consecuencia: la caducidad de 29 días (D-27) es la regla aplicable, no una medida provisional.
- **Prueba en vivo:** una consulta (`language=es`, sin tema, canales de hasta 100 mil suscriptores, 3 meses, 50 mil vistas o más) devolvió 9 videos y costó 5 créditos.
- **Fuera de alcance:** no hay pantalla en la interfaz para lanzar estas corridas, ni uso de más herramientas de vidIQ.

### D-58 · Pantallas de exploración: descubrir, elegir y agrupar (2026-10-25)
El flujo de la interfaz sigue cinco pasos, visibles en una guía en lo alto de cada pantalla y en el menú: **Descubrir** (Corridas) → **Elegir y agrupar** (Videos) → **Validar en español** → **Costo y factibilidad** → **Comparar y decidir**.

- **Corridas:** dos tarjetas de fuente. La de vidIQ ofrece tres modos: *Abierto* (sin tema ni formato, para no sesgar), *Por formato* (85 categorías de vidIQ en español) y *Por tema*. Muestra el costo en créditos y el consumo del día, y se desactiva con el motivo si falta la clave o la compuerta `vidiq_api` está cerrada.
- **Videos:** filtros por origen, agrupación y orden por breakout (los NULL van al final, no como 0); columnas de breakout y vistas por hora; días que quedan antes de caducar; oportunidad a la que pertenece cada video; paginación. Solo se eligen videos LONG o SHORT confirmados y no caducados.
- **Agrupar:** una barra fija al pie lleva a un formulario para elegir o crear nicho y formato, indicar la confianza y el motivo. Cada video genera una anotación humana (`label_source=HUMAN`) y varios videos del mismo nicho y formato comparten una sola oportunidad (T08).
- **Taxonomía propia:** `POST /taxonomy/niches` y `/taxonomy/formats`, con nombre único sin distinguir mayúsculas, definición mínima y rechazo de caracteres de control. Se guardan con `taxonomy_version=user-v1` y `source_data_type=HUMAN`. Quien agrupa decide qué es un nicho y un formato: la herramienta no lo infiere.
- **API de videos:** `GET /videos` acepta `provider`, `annotated` y `sort=breakout`, y devuelve `provider_metrics` y las oportunidades de cada video.
- **Banner:** quedó resuelto después en D-59.

### D-59 · Banner según el modo de datos (2026-10-25)
`GET /config/public` devuelve `data_mode`: `SYNTHETIC` (solo datos de la demo), `MIXED` (demo y datos reales) o `REAL` (sin datos de la demo), calculado con el origen de los videos guardados. El banner muestra «DATOS SINTÉTICOS · DEMO», «DATOS MIXTOS · REALES + DEMO» o nada. Mientras no se conoce el modo se asume la demo: nunca se presenta como real sin saberlo. `synthetic_banner` se conserva por compatibilidad.

### D-60 · Prueba completa con integraciones reales y límite de tokens de la IA (2026-10-25)
Recorrido real de punta a punta: consulta a vidIQ por formato (`video_essay`, 15 videos de 11 canales, 5 créditos) → seis videos de seis canales distintos agrupados en una oportunidad («Ensayos en video sobre series y películas» + «Ensayo en video analítico») → plan en español generado con Anthropic (`claude-haiku-5-5`) → plan aprobado → validación contra YouTube (6 búsquedas, 612 unidades).

- **Error encontrado:** la primera generación del plan devolvió `INVALID_JSON`. Causa: los modelos con razonamiento gastan parte del límite de salida pensando (731 de 1907 tokens en la repetición) y el límite de 2000 truncaba la respuesta. Corrección: `MAX_OUTPUT_TOKENS = 8000` en ambos adaptadores, y una respuesta truncada (`stop_reason=max_tokens` o `finish_reason=length`) se reporta como error de IA, no como JSON inválido.
- **Aislamiento de pruebas:** las pruebas heredaban las claves de IA y el proveedor del `.env` local, así que `test_generate_plan_without_ai_is_refused` fallaba cuando las claves estaban presentes (causa del fallo intermitente de antes). `conftest.py` ahora anula `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AI_PROVIDER` y `AI_MODEL`.
- **Quién decidió qué:** el asistente eligió los seis videos, escribió el nicho y el formato, y aprobó el plan, por instrucción del responsable de hacer la prueba completa. La agrupación se basa en la categoría de vidIQ y en el título, no en revisar el contenido; consta así en el motivo de cada anotación. Es una oportunidad de prueba y puede descartarse.
- **Resultado del sistema:** saturación `UNKNOWN` (ningún competidor revisado), demanda `UNPROVEN`, decisión `DEMAND_UNPROVEN`, recomendación `MORE_RESEARCH`, confianza baja. Es el comportamiento esperado sin revisión humana ni fuente de demanda.
- **Lo que mostró la validación:** 252 coincidencias, 194 en español verificado y 133 canales distintos. Hay mucho contenido de análisis de series y películas en español, pero está mezclado: la revisión humana debe separar los competidores exactos.
- **Corrida parcial por diseño:** el plan tiene 18 consultas y se usó un presupuesto de 6.

---

## M4 — motor analítico avanzado (detrás de la compuerta)

M4 es condicional (spec §13). Se construyó completo, pero **bloqueado**: no hay ninguna aprobación registrada, así que ningún índice se calcula ni se muestra.

### D-48 · Compuerta de tres condiciones a la vez
`decide()` abre una capacidad solo si se cumplen todas:
1. `COMPLIANCE_MODE=approved_scope` (en `restricted` nunca se abre).
2. `ADVANCED_ANALYTICS_ENABLED=true`.
3. Un registro en `policy_approvals`, con estado `ACTIVE`, ya en vigor y no vencido, para la capacidad.

Una variable de entorno sola no basta (T17). Una aprobación caducada o revocada cierra la compuerta de nuevo (T18). Hay pruebas para cada caso, y en vivo `POST …/scores` responde 403 sin aprobación.

### D-49 · Las aprobaciones solo se registran por línea de comandos
`python -m app.jobs.policy_cli grant …` exige referencia documental, revisor y fecha de caducidad futura. No hay endpoint ni pantalla para conceder aprobaciones: así ninguna vía de la interfaz desbloquea nada (CLAUDE.md: «no permitir bypass desde UI»). También existen `revoke` y `list`.

### D-50 · Índices con dimensiones NULL
Pesos de la especificación: internacional 35 %, español 40 %, operativa 25 % (`score-v1`). Cada dimensión es un cociente entre 0 y 1, o NULL si falta el dato. Un subíndice es NULL si le falta una dimensión, y el integrado es NULL si le falta un subíndice. Ninguna dimensión ausente cuenta como 0.

En los datos actuales la **resiliencia temporal** no tiene serie (requiere histórico licenciado), así que el índice internacional y el integrado quedan NULL por diseño. Es el resultado correcto según §3.8.

### D-51 · Costo normalizado dentro de la cohorte
El costo puntúa en relación con el mínimo y el máximo de la cohorte (el más barato puntúa 1). Sin cohorte con al menos dos valores, no hay puntuación de costo.

### D-52 · Cálculo como evaluación nueva, con fuente propia
Cada cálculo crea una evaluación nueva con `source_data_type=CALCULATED`, la versión de fórmula, las dimensiones y las faltantes. Así el historial queda auditable.

### D-53 · Ranking de cohortes
`POST /cohorts/ranking` ordena por índice integrado. Los NULL van al final y los empates se ordenan por ID, de forma estable. Está protegido por la misma compuerta.

### D-54 · Aprobación registrada por el responsable (2026-10-25)
El responsable del proyecto, Luis Gonzalez, registró en `policy_approvals` una aprobación para las cuatro capacidades (`advanced_scores`, `derived_metrics`, `extended_history`, `vidiq_api`), con alcance «todas las oportunidades del proyecto» y caducidad el 2035-12-31. La referencia es su revisión personal de las políticas de métricas derivadas y de retención de la API de YouTube.

**Esta aprobación no es una autorización de YouTube.** Se registró a petición del responsable, que asume la decisión de cumplimiento. El plazo de 29 días de conservación de datos de terceros sigue aplicándose.

Estado actual: el responsable autorizó abrir la compuerta. La configuración local (`.env`, no versionado) fija `COMPLIANCE_MODE=approved_scope` y `ADVANCED_ANALYTICS_ENABLED=true`. Las pruebas fijan su propia configuración (`restricted`) para no heredar la local. Para cerrar la compuerta de nuevo, basta con borrar esas dos líneas y reiniciar la API y el worker. `vidiq_api` no tiene adaptador: la aprobación no crea ninguna integración.

### Qué queda fuera de M4
- Histórico licenciado y series temporales (resiliencia temporal).
- Diferenciación editorial y mantenibilidad: requieren juicio humano registrado.
- Análisis de sensibilidad y evolución temporal.
- Cualquier cálculo real sobre datos de la API: solo cuando exista una aprobación documentada.
