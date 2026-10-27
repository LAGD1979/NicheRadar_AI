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

### D-61 · Replicación internacional calculada con datos reales (2026-10-25)
Hasta ahora los estados «Replicado», «Prometedor» y «Caso aislado» solo existían en la demo. `domain/replication.py` (reglas `repl-v1`, función pura) los calcula a partir de los videos que una persona agrupó en la oportunidad, con las reglas de la especificación §3.4:

- **REPLICATED:** 3 o más canales independientes, reparto (2 o más videos por canal, o 6 o más videos), 3 o más semanas ISO distintas y concentración del mayor canal menor de 60 % de los videos exitosos.
- **PROMISING:** 2 o más canales y 4 o más videos en 2 o más semanas.
- **SINGLE_OUTLIER:** un solo canal o creador, o un solo video exitoso.
- **UNKNOWN:** sin videos relevantes, sin vistas ni suscriptores para medir el éxito, o muestra insuficiente (por ejemplo 3 videos). Nunca se trata un dato faltante como cero.

Un video «exitoso» tiene al menos 50 000 vistas (`long_video_views_soft_min`) y es de un canal de hasta 50 000 suscriptores (`candidate_channel_subscribers_soft_max`). Cuentan solo las anotaciones con confianza alta o media; las de confianza baja se excluyen y se informa. Un video anotado dos veces cuenta una.

- **Compuerta:** es una métrica derivada, así que corre solo si `derived_metrics` está abierta (D-48). Si no, la sección internacional queda como estaba y la API responde 403 al pedirla.
- **Cuándo se calcula:** al agrupar un video (`POST /videos/{id}/annotations`, que ahora devuelve `replication_state`) y a pedido (`POST /opportunities/{id}/replication/refresh`). Cada cambio crea una versión nueva de la evaluación; recalcular sin cambios no crea nada.
- **Evidencia:** cada video agrupado genera una fila de evidencia internacional (`INTL_EXAMPLE`), con el motivo de la persona, y la ficha la muestra.
- **Caducidad:** un video purgado a los 29 días deja de contar.
- **Límites declarados en cada resultado:** `independence_verified=false` (un canal distinto no prueba un creador distinto; canales espejo pendientes, T12; el campo `creator_group` permite corregirlo cuando exista esa revisión) y `sample_bias_warning` (los videos salen de búsquedas y de una selección humana, no de una muestra del universo).
- **Resultado real:** la oportunidad de prueba de D-60 pasó a «Replicado» (6 canales, 6 videos, 4 semanas, concentración 17 %) y la recomendación subió de «Investigar más» a «Validar demanda con piloto». Esa replicación se apoya en seis videos que el asistente eligió por título y categoría de vidIQ.
- **No incluido:** la métrica de `PROMISING`/`REPLICATED` no usa el desempeño frente al promedio del propio canal (mínimo 5 videos comparables) ni el desglose por idioma; la tracción, la persistencia y la resiliencia temporal siguen sin calcularse.

### D-62 · Tres dimensiones de M4 sin depender de Trends (2026-10-25)
Las dimensiones `exito_accesible`, `diferenciacion` y `mantenibilidad` del índice (`score-v1`) dejan de estar fijas en NULL.

- **Éxito accesible a canales pequeños** (`domain/small_channel_access.py`, regla `small-access-v1`): entre los competidores **exactos** que una persona revisó y están verificados en español, la fracción que son canales de hasta 50 000 suscriptores con 50 000 vistas o más (umbrales de `research.yaml`). Exige al menos 3 competidores con vistas y suscriptores conocidos. Sin competidores exactos o con muestra insuficiente queda en NULL con su estado (`NO_EXACT_MATCHES`, `INSUFFICIENT_SAMPLE`); nunca cero. Se guarda en `spanish_json.small_channel_access` cada vez que se recalcula la evaluación en español.
- **Diferenciación editorial y mantenibilidad** (`POST /opportunities/{id}/editorial`): dos valoraciones humanas, cada una con nivel y motivo de 20 o más caracteres. Diferenciación: ALTA 1,0, MEDIA 0,6, BAJA 0,2. Mantenibilidad (esfuerzo por mantener el contenido al día): POCO 1,0, MODERADO 0,6, MUCHO 0,2. Se guardan en `feasibility_json.editorial`, y guardar la factibilidad ya no las borra.
- **Interfaz:** panel «Valoración editorial» en la pestaña de producción y una línea de éxito accesible en «Mercado español».
- **Efecto actual:** el índice integrado sigue en NULL para toda oportunidad. Faltan `resiliencia_temporal` (sin serie histórica licenciada), `demanda_observable` (sin fuente) y, en oportunidades reales, las valoraciones humanas y la revisión de competidores.
- **Pendiente conocido:** `traccion` usa el estado de replicación como sustituto, igual que `replicabilidad`: cuenta dos veces la misma señal. Debe sustituirse por una medida propia de tracción.
- **Pendiente conocido:** el éxito accesible no se compara contra un estrato temporal (spec §10.4); usa umbrales fijos.

### D-63 · Demanda con HasData y vidIQ, y persistencia de videos (2026-10-26)
Se implementó lo investigado sobre vidIQ y se añadió Google Trends por la API REST de HasData. Con esto la demanda en español y la resiliencia temporal dejan de ser NULL fijos.

**Autorización de HasData.** El responsable (Luis Gonzalez) indicó el 2026-10-26 marcar la fuente como autorizada. Se registró por línea de comandos en `policy_approvals`: capacidad `google_trends`, proveedor `hasdata`, vigente **hasta 2027-10-26** (el asistente eligió un año porque el responsable no indicó caducidad; se ajusta revocando y registrando otra). **No es una autorización de Google.** HasData obtiene los datos de Google Trends por scraping en su lado; el responsable asume esa decisión de cumplimiento, como en D-54. Los datos se tratan como de terceros: caducan a los 29 días.

**HasData (REST).** `providers/hasdata.py`: `GET https://api.hasdata.com/scrape/google-trends/search` con `x-api-key`; cada consulta cuesta 10 créditos de HasData. Se usa `gprop=youtube` (búsquedas dentro de YouTube) y `date=today 12-m`. La respuesta real trae `interestOverTime.timelineData[]` (semanal; `hasData=false` es desconocido, no cero) y `relatedQueries.top/rising`. Tope diario local de 30 consultas (`HASDATA_DAILY_CALL_LIMIT`). La clave sale de `HASDATA_API_KEY`. El servidor MCP de HasData (`.mcp.json`, limitado a Trends) es solo para explorar desde Claude; el backend usa la REST.

**vidIQ ampliado.** `keyword_research` (volumen mensual estimado, crecimiento; `countryVolume: null` = desconocido) y `video_stats` (serie diaria de vistas desde la publicación). 5 créditos cada una, con el mismo tope diario de créditos.

**Señales de demanda** (`domain/demand_signals.py`, `demand-v1`). La demanda es «Observada» con 2 o más señales de **familias distintas**; varias palabras clave de una misma fuente cuentan una vez.
- `google_trends`: presente si el índice relativo de las últimas 13 semanas es de 10 o más y no cayó por debajo de 0,6 de la base; con menos de 26 semanas con dato es desconocida (nunca «ausente»).
- `vidiq_keywords`: presente con 1000 o más búsquedas al mes y sin caída fuerte.
- `youtube_consumption`: 3 o más competidores exactos revisados con 50 000 vistas o más (métrica derivada: exige `derived_metrics`).
Las observaciones se guardan en `demand_observations` (migración 0006) con procedencia y caducidad de 29 días; se usa la más reciente por fuente, palabra clave y país. `record_assessment` pasa de fijar 0 señales a contarlas.

**Persistencia** (`domain/persistence.py`, `persist-v2`). Vistas por día de la **segunda semana** sobre las de la **primera**, ambas desde la publicación, con tope en 1 (spec: «pérdida o ganancia de velocidad en 7–14 días»). Exige historial que empiece cerca de la publicación y llegue al día 15. El agregado es la mediana de al menos 3 videos y alimenta `resiliencia_temporal`. La primera versión (`persist-v1`: última semana contra la mejor) dependía de la edad del video y dejaba a todos cerca de 0; se descartó al verla con datos reales y las medidas anteriores se recalculan solas.

**Compuertas.** `google_trends` para HasData, `vidiq_api` para vidIQ y `derived_metrics` para consumo y éxito accesible. También se cerró una omisión de D-62: el éxito accesible a canales pequeños no pasaba por `derived_metrics`.

**Resultado real** (oportunidad de prueba de D-60): demanda **Observada** (Trends + palabras clave de «video ensayo»: índice relativo reciente 65 de 100 y 22 318 búsquedas al mes, +55,9 %), persistencia mediana **0,53** (de 0,24 a 1,0 entre los 6 videos) e índice internacional **92,98**, el primero con valor sobre datos reales. El integrado sigue en NULL: faltan oferta abordable, éxito accesible, diferenciación y la dimensión operativa completa (revisión y valoraciones humanas).

**Límites conocidos.**
- «análisis de series» dio 0 búsquedas al mes en vidIQ y pocos datos en Trends: términos de poco volumen, con tilde o en español pueden salir vacíos. Se tratan como no alcanzados o desconocidos, no como prueba de ausencia de demanda.
- El índice de Trends es relativo y no comparable entre palabras clave consultadas por separado.
- `traccion` sigue usando la replicación como sustituto (doble conteo con `replicabilidad`).
- Las evaluaciones anteriores conservan los derivados aunque los datos de origen caduquen (como en D-61 y D-62).

### D-64 · Revisión asistida de competidores y cobertura mínima de revisión (2026-10-26)
La revisión de competidores era el cuello de botella de la validación en español (186 videos en la oportunidad de prueba) y tenía una falla: bastaba revisar cualquier coincidencia, sin ningún exacto, para que la saturación saliera «Baja».

**Cobertura mínima de revisión.** `spanish_market.saturation_state` exige haber revisado al menos el **80 %** de los videos en español (`spanish_review_min_share` en `research.yaml`) para decir «Baja» o «Media»; con menos queda «Desconocida» con el motivo `ES_REVIEW_COVERAGE_LOW` y la decisión `INSUFFICIENT_EVIDENCE`. «Alta» (5 o más exactos confirmados) sí vale con una revisión parcial: seguir revisando solo puede sumar competidores, así que es una cota inferior. Las evaluaciones guardan `review_coverage` (videos, revisados, parte, mínimo).

**Se cuenta por video, no por búsqueda.** Un mismo video hallado por dos búsquedas era dos «competidores exactos». Ahora la cobertura cuenta videos únicos y revisar una coincidencia aplica la decisión a todas las búsquedas que encontraron ese video. `GET /competition` devuelve un renglón por video (con `queries_count`).

**La IA propone, una persona decide** (`domain/competitor_review.py`, `services/competitor_ai_service.py`, prompt `P3-1`).
- Para cada video en español sin revisar, la IA sugiere `EXACT`, `ADJACENT`, `GENERIC` o `FALSE_POSITIVE`, con confianza `HIGH`, `MEDIUM` o `LOW` y un motivo breve. Decide solo con el título, el canal, la duración y el idioma; no afirma lo que se ve en pantalla.
- La salida se valida con un esquema estricto: JSON válido, `source_id` entre los enviados (un ID inventado descarta el lote, T13), motivo sin enlaces. Los títulos viajan como datos dentro de un JSON y el prompt prohíbe obedecerlos (T14).
- La sugerencia se guarda en columnas `ai_*` de `discovery_matches` (migración 0007) y **nunca cuenta como revisión**: no cambia la saturación ni los exactos.
- Los lotes son de 20 videos. Si una respuesta se trunca por el límite de tokens (`ResponseTruncated`), el lote se parte en dos y se reintenta; si aun así falla, queda pendiente y se informa.
- `POST /opportunities/{id}/competition/ai-review` encola la corrida (`match_review`); exige IA configurada (409 `AI_NOT_CONFIGURED`) y videos pendientes (409 `NO_PENDING_MATCHES`).
- `POST /opportunities/{id}/competition/accept-ai` (`min_confidence` HIGH o MEDIUM) es la **aceptación en bloque**, una acción humana explícita con auditoría (`MATCHES_ACCEPTED_FROM_AI`). Nunca acepta confianza baja, marca la revisión como «aceptó sugerencia IA» y recalcula una sola vez.
- Precisión medida: `ai_assist.agreement` compara la sugerencia con las revisiones **individuales**; lo aceptado en bloque no cuenta, porque coincide por construcción (spec §13.3).

**Cohorte de costos sin datos sintéticos.** La normalización del costo usa solo oportunidades de la misma clase (reales con reales, demo con demo; el nicho sintético marca la demo). Con menos de dos costos no hay estrato y el costo no se puntúa: antes un único costo recibía 1,0 por defecto, contra la regla de D-51.

**Prueba real** (oportunidad de D-60, IA `claude-haiku-5-5`): 186 videos en español clasificados en 9 lotes. Sugerencias: 18 exactos, 91 cercanos, 25 genéricos y 52 falsos positivos; 64 de confianza alta, 99 media y 23 baja. Los 18 exactos son análisis con tesis sobre series, películas y personajes (anime, Harry Potter, Game of Thrones, Avatar), y los falsos positivos de confianza alta son noticias, música o videos sin relación. **Nada se aceptó**: la revisión sigue en 0 %. Si se aceptan las sugerencias de confianza alta habría 6 exactos y la saturación pasaría a «Alta» (se necesitan 5), es decir, el mercado en español ya tiene competencia directa.

**Límites.** La IA solo ve títulos y canales, no el contenido; su precisión real se mide cuando el responsable revise individualmente. El umbral del 80 % es una heurística por calibrar.

### D-65 · La demo deja de convivir con los datos reales (2026-10-26)
Los datos sintéticos (`synthetic_v1`) siguen existiendo, pero ya no tienen que estar en la base de trabajo.

- **Sigue siendo necesaria** para las pruebas automáticas (que usan su propia base `nicheradar_test`), para los E2E y para el modo DEMO que exige `CLAUDE.md` (funcionar desconectado de servicios reales).
- **`DEMO_MODE`** ahora controla la carga: con `DEMO_MODE=false` el servicio `migrate` no carga la demo (`seed_skipped`), la corrida DEMO responde 409 `DEMO_DISABLED`, el botón desaparece de Corridas y el proveedor sintético figura como desactivado. Por defecto sigue en `true` (una instalación nueva ve la demo). `docker-compose.yml` pasa `DEMO_MODE` al backend y una variable del entorno gana al `.env`.
- **`python -m app.demo.purge`** quita la demo de una base existente. Por defecto **solo simula**; con `--apply` borra en una transacción. Borra los registros del fixture y todo lo que cuelga de sus oportunidades (evaluaciones, evidencia, anotaciones, planes, búsquedas, coincidencias, costos, demanda). **No toca** videos ni canales reales (un canal de la demo con videos reales se conserva), oportunidades reales ni corridas. Si una oportunidad real usa un nicho o formato de la demo, se detiene (`DETENIDO`) y la lista. Es idempotente.
- **Los E2E** corren con `scripts/e2e.ps1`: proyecto de Compose propio (`nicheradar_e2e`), base y puertos propios (15433, 8001, 5174), demo cargada y sin claves reales; al terminar elimina el entorno. Antes corrían contra la base de trabajo y exigían que tuviera la demo.
- **Aplicado el 2026-10-26** sobre la base local, con respaldo previo en `backups/nicheradar_antes_de_quitar_demo_*.sql` (carpeta fuera de Git). Se borraron 8 oportunidades, 20 videos, 10 canales, 5 nichos, 4 formatos, 12 evidencias, 10 evaluaciones, 4 planes, 100 coincidencias, 2 búsquedas, 1 anotación y la corrida de la carga. Se conservaron 417 videos reales, 288 canales reales, la oportunidad real y 16 corridas. El `.env` local fija `DEMO_MODE=false`. La base quedó en modo de datos REAL y sin banner.
- **Para volver a tener la demo:** poner `DEMO_MODE=true` y reiniciar (el servicio `migrate` la carga de nuevo), o restaurar el respaldo.

### D-66 · Consultas comparables de Trends y topes de HasData según el saldo real (2026-10-26)
**Saldo real.** El panel de HasData muestra una prueba con 920 créditos disponibles hasta el 2026-11-01. Después el plan vuelve al gratuito: **1.000 créditos al mes** (100 consultas de 10 créditos) y concurrencia 1; los créditos de la prueba sin usar caducan. Un crédito solo se cobra si la consulta tiene éxito.

**Topes locales (`config.py`).** `HASDATA_DAILY_CALL_LIMIT` baja de 30 a **90**, igual que el mensual, para que el límite que importe sea el saldo del mes y no una restricción diaria, y se añade `HASDATA_MONTHLY_CALL_LIMIT=90` (deja 10 consultas de margen sobre el plan gratuito). El mes se cuenta por calendario UTC, no por el ciclo de facturación de HasData; el margen cubre la diferencia. Las consultas hechas fuera del sistema (por ejemplo desde el MCP) no se cuentan aquí. `GET /usage/hasdata` y el panel de Demanda muestran el uso diario y mensual.

**Términos comparables.** Probado en vivo (10 créditos): `dataType=timeseries` acepta varios términos separados por coma en una sola llamada y cuesta lo mismo que uno. Cada punto trae un valor por término, con su nombre y `hasData`. `HasDataClient.compare_interest` pide hasta 5 términos juntos y devuelve una serie por término; el índice de cada uno es relativo **al más fuerte del grupo**, así que los términos de una misma llamada se pueden comparar y los de llamadas distintas no. Los términos se identifican por el nombre que devuelve HasData y, si no coincide, por la posición. Un término sin datos sigue siendo desconocido, nunca cero. El nombre del término no puede llevar coma.

**Efecto en la señal.** Frente a un término más fuerte, un índice bajo no prueba que falte demanda. Por eso, en una medición de varios términos, un resultado «índice relativo bajo» pasa a `UNKNOWN` con motivo `LOW_IN_COMPARISON` (medido solo seguiría siendo `NOT_PRESENT`). Cada observación guarda `comparison_group`, `terms` y `share_of_leader` (su índice reciente como porcentaje del más fuerte). Las consultas relacionadas siguen siendo de un término (una llamada por término).

**Sin repetir gasto.** Si ya hay una medición vigente (menos de `HASDATA_REUSE_DAYS`=7 días) de los **mismos términos en el mismo grupo**, no se vuelve a pedir; la corrida lo cuenta como reutilizado. Un grupo distinto, aunque comparta un término, no es comparable y se mide de nuevo. La casilla «Repetir aunque haya una medición reciente» (`force`) lo omite. Se envía `tz=0` siempre para alinear las semanas en UTC.

**Costo.** Ahora una medición de N términos cuesta 1 consulta (10 créditos), más N si se piden las relacionadas. Antes costaba N.

**Saldo visible.** En lugar de depender de un tope diario restrictivo, el encabezado muestra siempre un indicador por herramienta (YouTube, vidIQ, HasData): barra y cantidad restante, ámbar bajo el 20 % y rojo al agotarse (`BalanceMeters`, `balance.ts`). Son los contadores locales contra los topes configurados, no el saldo real del proveedor. Los saldos se leen al cargar la página, al terminar una corrida y con el botón «Refrescar saldos»; no se sondean. El tope diario de HasData sube a 90 (igual al mensual) para que lo que se vea sea el saldo del mes.

**Límites conocidos.** Al medir un término muy pequeño junto a uno muy grande, el pequeño queda en `UNKNOWN`; para decidir su demanda hay que medirlo solo. Los términos medidos antes de este cambio no tienen grupo y se vuelven a medir la primera vez.

### D-67 · Asistente de IA por oportunidad (2026-10-26)
Una pestaña «Asistente» en la ficha de la oportunidad: un asesor que responde preguntas sobre la oportunidad y sugiere pasos. **Solo lectura y asesor, no decisor** (decisión del responsable): no cambia datos, no dispara corridas y no dice «elija» ni «descarte».

**Contexto agregado y anónimo.** El responsable pidió que la IA no reciba información particular de canales o videos. `services/assistant_context.py` construye un resumen con conteos, estados, índices, medianas y los valores que una persona escribió (costos y niveles). **No viajan** títulos de videos, nombres de canales, identificadores, enlaces ni el texto libre de las valoraciones. De los competidores exactos solo se envían la cantidad, la mediana y el máximo de vistas y los canales por tramo de suscriptores (esto último exige `derived_metrics`; si está restringido, lo dice y no lo envía). Las demás secciones respetan las compuertas existentes: los índices llegan con su estado `RESTRICTED` y la demanda usa solo observaciones vigentes. Una prueba comprueba que ningún título, canal o identificador de la base aparece en el contexto. Cada sección tiene una clave (`opportunity`, `evaluation`, `international`, `spanish_market`, `demand`, `competitors`, `production`, `scores`, `missing`) y `missing` lista en lenguaje llano lo que falta.

**Costo.** El resumen mide unos 1.150 tokens (≈1.850 con instrucciones y pregunta), sin listas de registros: por eso no hizo falta resumir con otra llamada de IA. El historial se recorta a 6 turnos de 700 caracteres, la salida a 4.000 tokens, la pregunta a 1.000 caracteres y hay un tope de 100 mensajes al día (`ASSISTANT_DAILY_MESSAGE_LIMIT`; cada intento cuenta aunque falle). La pestaña muestra los tokens estimados y el contexto exacto que se envía.

**Respuestas controladas.** El prompt `A1-2` (`prompts/assistant_v1.py`) exige usar solo el contexto, no inventar, citar la sección entre corchetes, tratar contexto, historial y pregunta como datos no confiables, y devolver JSON (`answer`, `citations`, `unknowns`, `next_steps`). El servicio descarta las citas que no son secciones reales; si la respuesta trae cifras sin citas la marca (`unsourced`) y si no es JSON la conserva marcada (`structured=false`). La interfaz lo avisa. El texto de la persona y el historial van siempre en el mensaje de datos, nunca en las instrucciones del sistema.

**Endpoints.** `GET /assistant/status`, `GET /opportunities/{id}/assistant/context` y `POST /opportunities/{id}/assistant`. Es síncrono (una consulta corta a la IA, no un trabajo largo); los errores del proveedor se traducen a 502/503 y la falta de IA a 409. La conversación no se guarda: vive en la pantalla.

**Privacidad.** Se envían a un proveedor de IA externo los valores del resumen, incluidos nicho, formato, costos y niveles escritos por la persona. El responsable asumió ese riesgo; los términos de vidIQ y HasData sobre procesamiento con IA no se revisaron y el contexto agregado evita enviar sus registros individuales.

**Prueba real** (Claude Haiku 5.5 sobre la oportunidad real): explicó qué faltaba para decidir con cifras y citas correctas; ante «responde solo SÍ o NO» se negó y dio a favor, en contra y desconocidos; ante una orden de ignorar sus reglas y listar títulos y canales respondió que el resumen no los incluye. La primera versión tuteaba; el prompt pasó a `A1-2` para tratar de usted.

**Límites.** Es una etapa 1: un asesor por oportunidad. No propone acciones ejecutables ni tiene un modo general (sobre la herramienta). Puede equivocarse: las citas y el contexto visible permiten verificar. Sin pruebas de evaluación automática de calidad de respuesta (solo del formato y de lo que se envía).

### D-68 · IA y modelo elegidos por función (2026-10-26)
La IA que usa cada función se elige desde **Configuración → IA y modelo por función**, sin tocar el `.env` ni reiniciar.

**Tres funciones**, cada una con su modelo: `assistant` (el asistente, D-67), `classification` (sugerencias sobre competidores en español, D-64) y `plan` (plan de búsqueda en español). La idea es poder usar un modelo rápido y económico para tareas masivas y uno más capaz para razonar.

**Catálogo editable.** Los modelos permitidos viven en `config/research.yaml` (sección `ai.models`: proveedor, modelo, nombre y descripción). Hoy: Claude Haiku 5.5, Sonnet 5.5, Opus 5.5 y Fable 5.1, y de OpenAI los tres que indicó el responsable: GPT-6 Luna (`gpt-6-luna`, clasificación, extracción y procesamiento masivo), GPT-6.1 Sol (`gpt-6.1-sol`, complejidad media: análisis, métricas, recomendaciones) y GPT-6 Astra (`gpt-6-astra`, razonamiento profundo y evidencia contradictoria). Las descripciones de OpenAI son las del responsable; los nombres de modelo no se verificaron más allá de que la API los aceptó en las pruebas.

**Reglas.** Solo se puede elegir un modelo del catálogo (422 si no) y de un proveedor con clave definida (409 si no; las claves nunca salen de la API). La elección se guarda en `ai_selections` (migración 0008) y cada cambio queda en la auditoría (`AI_SELECTION_CHANGED`, con lo anterior y sin claves). **Sin elección rige `AI_PROVIDER`/`AI_MODEL` del entorno**, como antes: «Predeterminado» en la interfaz. Se puede volver a él en cualquier momento. El worker lee la elección en cada corrida, así que un cambio rige en la siguiente.

**API.** `GET /ai/settings` (funciones, elección vigente y catálogo con disponibilidad), `PUT /ai/settings/{función}` y `DELETE /ai/settings/{función}`. Las corridas de plan y de clasificación guardan en sus parámetros el modelo que usaron, y cada sugerencia sigue registrando `ai_model`. Los dobles de prueba (`make_ai`) siguen mandando sobre la elección.

**Hallazgo con OpenAI.** Los modelos GPT-6 responden 400 a `temperature: 0` («solo admite el valor por defecto»), igual que Anthropic en D-56. El cliente de OpenAI ya no envía `temperature`.

**Prueba real.** Con la oportunidad real, el asistente respondió con los tres modelos de OpenAI (≈10 s cada uno): JSON válido, citas de secciones correctas y, ante «responde solo SÍ o NO», se negó a decidir y dio a favor, en contra y desconocidos. Quedó probada la elección con `PUT`; la clasificación y el plan con OpenAI se probaron antes (D-55) pero no con estos modelos.

**Límites.** Cambiar de modelo a mitad de trabajo mezcla sugerencias hechas por modelos distintos (cada una conserva el suyo). No hay estimación de costo por modelo: los precios no están en el repositorio y no se inventan.

### D-69 · M5, primer tramo: programación, purga automática, seguimiento y alertas (2026-10-27)
Primer tramo del hito M5 (radar continuo). Se construyó en la rama `m5-programacion-y-seguimiento`, creada desde el tag `m4-listo-para-probar` para no mover el pull request de M4. Migración 0009.

**Trabajos programados** (`scheduler_service`, tabla `scheduled_jobs`). El reloj vive en la aplicación: el worker llama a `tick` cada 30 segundos y encola como corridas normales los trabajos vencidos. Hay tres, todos **sin costo externo**: `retention_purge` (cada 24 h; la purga de 29 días ya existía pero solo se ejecutaba a mano), `alerts_check` (cada 6 h) y `watchlist_recheck` (cada semana). Intervalo y activación se cambian en Configuración, y «Ejecutar ahora» encola uno a mano. Lo que gasta cuota o créditos (descubrimiento, demanda, validación, IA) **no se programa**: sigue siendo una acción explícita. Garantías: bloqueo `FOR UPDATE SKIP LOCKED` (dos workers no encolan el mismo trabajo), tras una caída se ejecuta una sola vez y no una por intervalo perdido, y no se encola un trabajo mientras otra corrida del mismo tipo siga en cola o ejecutándose. Un fallo del reloj se registra y no detiene al worker. Probado en vivo: los tres se ejecutaron solos al arrancar y reiniciar el worker no los repitió.

**Alertas** (`alerts_service`, tabla `alerts`). Solo nacen de hechos guardados y llevan una `dedupe_key`, así que una revisión repetida no las duplica. Del sistema: `QUOTA_WARNING` (YouTube, vidIQ o HasData al 80 % de su tope, y de nuevo al agotarse), `DATA_STALE` (datos de terceros que caducan en 3 días), `POLICY_REVIEW_REQUIRED` (autorización que vence en 30 días o ya venció) y `SOURCE_UNAVAILABLE` (corrida rechazada por una credencial; el mensaje no incluye claves). De una oportunidad: `NEW_INTERNATIONAL_PATTERN`, `SPANISH_DEMAND_SIGNAL`, `OPPORTUNITY_CONFIDENCE_UPGRADE` y `SPANISH_COMPETITION_INCREASE`; esta última solo si en ambos momentos se había revisado al menos el 80 % (comparación confiable, spec §9.4). Una persona las marca como vistas; no se borran. El encabezado muestra cuántas hay abiertas (ámbar, o rojo si alguna es crítica) y el Resumen deja de mostrar textos fijos para mostrar las reales.

**Seguimiento** (`watchlist_service`, tablas `watchlists` y `review_actions`). Una oportunidad en seguimiento tiene prioridad, próxima revisión, notas y un plan de piloto (hipótesis, hasta 5 videos propuestos y métricas de éxito) que **escribe y mide el propietario**: no se inventan resultados. Guarda una *foto* de sus indicadores; la revisión semanal recalcula la replicación con los datos guardados, compara con la foto y avisa de los cambios. La foto solo se renueva cuando una persona pulsa «Marcar como revisada», para que los cambios se acumulen hasta que alguien los vea. Un conteo que pasa de ausente a presente cuenta como aumento solo si la oportunidad ya tenía evaluación. Quitar una oportunidad exige un motivo; todas las decisiones quedan en `review_actions` (solo se agregan, con la hora fijada por la aplicación).

**Interfaz.** Pantalla «Seguimiento» (alertas y tarjetas con cambios, notas y plan), botón «Añadir a seguimiento» en la ficha, sección «Trabajos programados» en Configuración e indicador de alertas en el encabezado.

**Pendiente de M5** (spec §13): límites de costo de IA por corrida con `PARTIAL_BUDGET_EXHAUSTED`, export licenciado, permisos de usuario y despliegue local seguro, prueba de carga pequeña, backup programado con restauración probada y checklist de operación. Tampoco se programa el descubrimiento semanal (`discover_international`) porque gasta cuota; si se quiere, debe ir con tope explícito.

### D-70 · Topes de tokens de IA (M5) (2026-10-27)
La especificación (§9.2) pide parar el gasto de IA al llegar a un presupuesto y mostrar `PARTIAL_BUDGET_EXHAUSTED`. Como **no hay precios de modelos en el repositorio** (y el responsable decidió no estimar saldo en USD), el presupuesto se mide en **tokens reales**, no en dólares.

**Uso real.** Los clientes de Anthropic y OpenAI guardan en `last_usage` los tokens que informa el proveedor (entrada y salida), también cuando la respuesta se trunca (que sí cuesta) y sin heredar el uso de una llamada anterior que falló. Si un proveedor no informa el uso, se registra una estimación de 4 caracteres por token marcada `ESTIMATED`; nunca se inventa un costo para una llamada fallida sin uso informado. En la prueba real, una consulta del asistente gastó 4.208 tokens frente a unos 2.200 estimados: los modelos que razonan consumen más de lo que se ve en el texto, por eso el contador usa el dato del proveedor.

**Dos topes** (`ai_budget_service`, una fila en `provider_usage` por llamada, función y modelo): `AI_DAILY_TOKEN_LIMIT` (1.000.000; suma de asistente, clasificación y plan) y `AI_RUN_TOKEN_LIMIT` (300.000 por corrida). Antes de cada llamada se revisan; si ya se alcanzaron, no se llama al proveedor y se lanza `BudgetExhausted` (`PARTIAL_BUDGET_EXHAUSTED`). Un tope se puede sobrepasar por la última llamada (se revisa antes, no después).

**Efecto por función.** La clasificación se detiene, conserva los lotes ya sugeridos y termina `PARTIAL` con ese código y los videos que quedaron sin sugerencia. El plan de búsqueda falla con el mismo código. El asistente responde 429 `AI_BUDGET_EXHAUSTED`. Los topes se pueden subir en el `.env`.

**Visibilidad.** El encabezado suma un indicador «IA» (tokens de hoy frente al tope diario, abreviados como «995,8 k / 1 M»), Configuración muestra el uso por función y el tope por corrida, `GET /usage/ai` lo expone y una alerta `QUOTA_WARNING` avisa al 80 % y al agotarse.

**Corrección.** El asistente no confirmaba la transacción tras la llamada, así que el uso de tokens se perdía; ahora confirma también en los errores.

**Límites.** No hay equivalencia en USD. El tope diario cuenta en días UTC, igual que los demás contadores locales; no es el saldo del proveedor.

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
