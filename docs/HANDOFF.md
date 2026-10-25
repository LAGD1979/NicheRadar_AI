# Traspaso: cómo retomar NicheRadar AI

Documento para cualquier sesión nueva (o para una persona). Complementa `CLAUDE.md`, `docs/IMPLEMENTATION_PROGRESS.md` y `docs/DECISIONS.md`. Aquí están las cosas que esos documentos no cubren: operación, configuración local y preferencias de trabajo.

## 1. Estado actual (2026-10-25)

- Hitos M0, M1, M2, M3 y M4 construidos y commiteados. Último commit: `ad9bcdb`.
- M4 (índices avanzados) **abierto** en este equipo: el modo `approved_scope` está en el `.env` local, y hay cuatro aprobaciones registradas por el responsable (D-54). No es una autorización emitida por YouTube.
- Los índices siguen en NULL porque no existe resiliencia temporal (histórico licenciado). Es intencional.
- Sin fuente de señales de demanda: ninguna oportunidad real llega a «listo para piloto».
- IA (Anthropic y OpenAI): implementada, **no probada** contra APIs reales (no hay claves de IA configuradas).

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
- E2E (con el stack arriba): `… --profile e2e run --rm e2e`
- Estado esperado: 229 pruebas backend, 15 frontend, 7 E2E pasando y 1 omitido (el omitido es esperado).

Para ver cambios sin reconstruir la imagen: montar el código con `-v "<ruta>\backend:/app"` en `run`.

## 4. Configuración local (no versionada)

- `.env` en la raíz: `COMPLIANCE_MODE=approved_scope` y `ADVANCED_ANALYTICS_ENABLED=true`. Para cerrar M4, borrar esas dos líneas y reiniciar `api` y `worker`.
- Las pruebas fijan su propia configuración (`restricted`), así que no dependen del `.env`.
- Aprobaciones de políticas: viven en la base de datos local. Se listan con `docker compose … run --rm --no-deps api python -m app.jobs.policy_cli list`. Se registran solo por línea de comandos (`grant`), nunca desde la interfaz ni la API.

## 5. Datos de este equipo que no están en Git

- `syn-opp-06` tiene una anotación real (el video «Stalingrado…») y una validación real en español. Mezcla datos reales y sintéticos. Conviene borrarla antes de cualquier demo limpia.
- Hay videos reales `OFFICIAL` de la búsqueda de M1. Caducan a los 29 días; la purga es manual (`kind=purge`).
- El banner sigue diciendo «DATOS SINTÉTICOS · DEMO» aunque haya datos reales. Pendiente.

## 6. Reglas que no se deben romper

- No hacer commit sin que el responsable lo pida.
- No registrar aprobaciones de políticas sin la referencia que indique el responsable, con su fecha y su caducidad.
- No inventar precios, cifras, estados de demanda ni resultados de IA.
- En compliance, la conclusión la decide el responsable. El asistente la documenta, no la sustituye.
- Los datos de terceros caducan a los 29 días, con o sin aprobación.

## 7. Pendientes conocidos

- Confirmar la cuota real del proyecto en Google Cloud (la especificación dice 1 unidad por `search.list`; la documentación oficial dice 100).
- Probar IA con una clave real (Anthropic u OpenAI).
- Probar una búsqueda grande y la reanudación con cuota real.
- Detección de canales espejo (T12).
- Scheduler automático y purga programada (M5).
- Revisión humana de 30 a 50 videos etiquetados (§13.3) para medir precisión.
