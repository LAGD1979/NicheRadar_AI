# Traspaso: cómo retomar NicheRadar AI

Documento para cualquier sesión nueva (o para una persona). Complementa `CLAUDE.md`, `docs/IMPLEMENTATION_PROGRESS.md` y `docs/DECISIONS.md`. Aquí están las cosas que esos documentos no cubren: operación, configuración local y preferencias de trabajo.

## 1. Estado actual (2026-10-25)

- Hitos M0, M1, M2, M3 y M4 construidos y commiteados. Último commit: `ad9bcdb`.
- M4 (índices avanzados) **abierto** en este equipo: el modo `approved_scope` está en el `.env` local, y hay cuatro aprobaciones registradas por el responsable (D-54). No es una autorización emitida por YouTube.
- Los índices siguen en NULL porque no existe resiliencia temporal (histórico licenciado). Es intencional.
- Revisión de competidores (D-64): en la pestaña «Mercado español» de la oportunidad de prueba hay 186 videos con sugerencia de la IA y ninguno revisado. «Aceptar sugerencias de confianza alta» pasa 6 exactos y deja la saturación en «Alta». La saturación exige revisar el 80 % de los videos en español.
- Topes de tokens de IA (D-70): `AI_DAILY_TOKEN_LIMIT` (1.000.000) y `AI_RUN_TOKEN_LIMIT` (300.000), en tokens reales del proveedor, no en USD. Indicador «IA» en el encabezado.
- M5, primer tramo (D-69): rama `m5-programacion-y-seguimiento`, creada desde el tag `m4-listo-para-probar` (el pull request de M4 va aparte). El worker ejecuta solo la purga diaria, las alertas y la revisión semanal del seguimiento; pantalla «Seguimiento»; alertas en el encabezado.
- IA por función (D-68): Configuración → «IA y modelo por función» elige proveedor y modelo del asistente, la clasificación y el plan; el catálogo está en `config/research.yaml` (`ai.models`). Sin elección rige `AI_PROVIDER`/`AI_MODEL` de `.env` (hoy Claude Haiku 5.5).
- Asistente de IA (D-67): pestaña «Asistente» en la ficha. Contexto agregado sin títulos ni canales; tope `ASSISTANT_DAILY_MESSAGE_LIMIT`=100.
- Trends comparables y topes (D-66): una medición de varios términos cuesta 1 consulta y da índices comparables; tope local de 90 al mes (el diario, también 90, no restringe) (el plan gratuito da 1.000 créditos al mes; la prueba de 920 créditos termina el 2026-11-01). Una medición reciente de los mismos términos se reutiliza.
- HasData (D-63): Trends por API REST. Clave en la variable de usuario `HASDATA_API_KEY`; autorización registrada hasta 2027-10-26 (capacidad `google_trends`). Para renovarla: `policy_cli revoke` y `grant`. El MCP de HasData (`.mcp.json`) es solo para explorar desde Claude.
- Demanda y persistencia reales (D-63): la ficha mide demanda con Trends y vidIQ y persistencia de videos con vidIQ. La demanda ya puede ser «Observada»; el índice internacional ya tiene valor con datos reales.
- M4: éxito accesible, diferenciación y mantenibilidad ya puntúan (D-62). El integrado sigue en NULL por resiliencia temporal y demanda.
- Replicación internacional calculada con datos reales (D-61): corre al agrupar videos y exige la capacidad `derived_metrics`. La oportunidad real de prueba está «Replicada».
- Sin fuente de señales de demanda: ninguna oportunidad real llega a «listo para piloto».
- **vidIQ (D-57):** adaptador MCP implementado y probado en vivo (`POST /research-runs` con `kind=vidiq`). Clave en la variable de usuario `VIDIQ_API_KEY`. El responsable revisó los términos de vidIQ: delegan el almacenamiento en los términos de la plataforma de origen, así que rige la caducidad de 29 días (D-57). Desde D-58 hay tarjeta en Corridas y agrupación en Videos.
- IA: los adaptadores de **OpenAI** (`gpt-4.1-mini`, D-55) y **Anthropic** (`claude-haiku-5-5`, D-56) se probaron en vivo el 2026-10-25 generando un plan de búsqueda. Las claves se leen de las variables de usuario `OPENAI_API_KEY` y `CLAUDE_API_KEY` (Compose acepta esta última como `ANTHROPIC_API_KEY`). El `.env` local deja activo Anthropic; para cambiar, editar `AI_PROVIDER` y `AI_MODEL` y recrear `api worker`.

## 1b. Manuales

- Guía de inicio rápido: `frontend/public/manual/inicio.html`.
- Manual de uso (funcional): `frontend/public/manual/funcional.html`.
- Manual técnico: `frontend/public/manual/tecnico.html`.
- Índice de ambos: `frontend/public/manual/index.html`.
- Se abren desde el menú lateral («Manuales») o en `http://localhost:5173/manual/`. También funcionan abriendo el archivo directamente, salvo los enlaces a la aplicación.

## 2. Operación en Windows (PowerShell)

- Ruta del proyecto: `C:\Luis\Dropbox\Negocios\202608_Youtube\2026\NicheRadar_AI_Claude_Code\NicheRadar_AI`.
- Usar siempre `docker compose --project-directory <ruta> …` desde cualquier carpeta.
- Arranque: `docker compose --project-directory <ruta> up -d --build`. La migración y el seed corren en el servicio `migrate`.
- Clave de YouTube: se lee de la variable de **usuario** de Windows `YOUTUBE_API_KEY`. Para pasarla a Compose en una sesión: `$env:YOUTUBE_API_KEY = [Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY','User')`. No mostrar su valor.
- No hay heredocs de bash en PowerShell. Para mensajes de commit largos: escribir un archivo de texto y usar `git commit -F <archivo>`.
- Si una herramienta devuelve «Remove-Item on system path … is blocked», es un error de la herramienta, no del proyecto: repetir con una ruta literal (`-LiteralPath`) o verificar el estado antes de actuar.

## 3. Comprobaciones (desde la carpeta del proyecto)

- Backend: `docker compose --project-directory <ruta> run --rm --no-deps api pytest -q`
- Lint y tipos backend: `… run --rm --no-deps api sh -c "ruff check app tests && ruff format --check app tests && mypy app"`
- Frontend: `… run --rm --no-deps frontend sh -c "npx eslint . && npx tsc --noEmit && npx vitest run"`
- E2E: `powershell -File scripts\e2e.ps1` (entorno aislado con la demo; no usa la base de trabajo)
- Estado esperado: 408 pruebas backend, 23 frontend, 11 E2E pasando y 1 omitido (el omitido es esperado).

Para ver cambios sin reconstruir la imagen: montar el código con `-v "<ruta>\backend:/app"` en `run`.

## 4. Configuración local (no versionada)

- `.env` en la raíz: `COMPLIANCE_MODE=approved_scope` y `ADVANCED_ANALYTICS_ENABLED=true`. Para cerrar M4, borrar esas dos líneas y reiniciar `api` y `worker`.
- Las pruebas fijan su propia configuración (`restricted`), así que no dependen del `.env`.
- Aprobaciones de políticas: viven en la base de datos local. Se listan con `docker compose … run --rm --no-deps api python -m app.jobs.policy_cli list`. Se registran solo por línea de comandos (`grant`), nunca desde la interfaz ni la API.

## 5. Datos de este equipo que no están en Git

- La base de trabajo ya **no contiene datos de la demo** (D-65): `DEMO_MODE=false` en el `.env` local y la demo se quitó con `python -m app.demo.purge --apply`. Respaldo previo en `backups/` (fuera de Git). Se perdió la anotación real que colgaba de `syn-opp-06`; los videos reales siguen.
- Hay videos reales `OFFICIAL` de la búsqueda de M1. Caducan a los 29 días; la purga es manual (`kind=purge`).
- El banner distingue datos sintéticos, mixtos y reales (D-59). Hoy muestra «MIXTOS».
- Hay una oportunidad real de prueba (D-60): «Ensayos en video sobre series y películas · Ensayo en video analítico». Sus 252 coincidencias esperan revisión humana; puede descartarse.

## 6. Reglas que no se deben romper

- No hacer commit sin que el responsable lo pida.
- No registrar aprobaciones de políticas sin la referencia que indique el responsable, con su fecha y su caducidad.
- No inventar precios, cifras, estados de demanda ni resultados de IA.
- En compliance, la conclusión la decide el responsable. El asistente la documenta, no la sustituye.
- Los datos de terceros caducan a los 29 días, con o sin aprobación.

## 7. Pendientes conocidos

- Confirmar la cuota real del proyecto en Google Cloud (la especificación dice 1 unidad por `search.list`; la documentación oficial dice 100).
- IA: probar reintentos (429/5xx), un modelo de razonamiento de OpenAI (`temperature`) y revisar la calidad de los planes generados.
- Probar una búsqueda grande y la reanudación con cuota real.
- Detección de canales espejo (T12): la replicación asume que canal distinto es creador distinto.
- Scheduler automático y purga programada (M5).
- Revisión humana de 30 a 50 videos etiquetados (§13.3) para medir precisión.
