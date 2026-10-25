# NicheRadar AI — M0 (demo sintético)

Radar local de oportunidades de contenido para YouTube en español. **Esta versión (M0) es una demo con datos sintéticos rotulados.** No consulta YouTube, no usa claves de API ni servicios de pago, y no contiene investigación real de nichos.

Documentos de referencia: [ESPECIFICACION_NICHERADAR_AI.md](ESPECIFICACION_NICHERADAR_AI.md), [CLAUDE.md](CLAUDE.md), [docs/IMPLEMENTATION_PROGRESS.md](docs/IMPLEMENTATION_PROGRESS.md), [docs/DECISIONS.md](docs/DECISIONS.md), [docs/TEST_PLAN.md](docs/TEST_PLAN.md).

## Requisitos

- Docker Desktop con Compose v2 o superior (probado con Docker 29.9.2 y Compose v5.6.1 en Windows 11).
- No hace falta Python ni Node en el host: todo corre en contenedores.

## Arrancar

Desde la carpeta del repositorio, en PowerShell:

```powershell
docker compose up -d --build
docker compose ps
```

Al arrancar, el servicio `migrate` aplica las migraciones y carga el dataset sintético (`synthetic_v1`) y termina con código 0. Después quedan activos:

| Servicio | Dirección en el host |
|---|---|
| Interfaz (React) | http://localhost:5173 |
| API (FastAPI, documentación en `/docs`) | http://127.0.0.1:8000 |
| PostgreSQL | 127.0.0.1:15432 |

Comprobar que la API está lista:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Debe responder `status: ready`.

Si el puerto 15432, 8000 o 5173 ya está en uso, defina `DB_HOST_PORT`, `API_HOST_PORT` o `FRONTEND_HOST_PORT` en un archivo `.env` (copie `.env.example`). En este equipo el puerto 5432 estaba bloqueado por Windows, por eso el valor por defecto es 15432.

## Pruebas

```powershell
docker compose run --rm --no-deps api pytest -q
docker compose run --rm --no-deps api sh -c "ruff check app tests && ruff format --check app tests && mypy app"
docker compose run --rm --no-deps frontend sh -c "npx eslint . && npx tsc --noEmit && npx vitest run"
docker compose --profile e2e run --rm e2e
```

- `pytest` usa PostgreSQL real en la base `nicheradar_test`, que se recrea en cada sesión, y no llama a red.
- `e2e` ejecuta tres flujos (demo → radar; ficha con pestañas; comparar cuatro) en escritorio y en móvil de 390 px. Requiere que el stack esté arriba.

## Reiniciar desde cero

```powershell
docker compose down -v
docker compose up -d --build
```

`down -v` borra el volumen de la base de datos. Como solo hay datos sintéticos, no se pierde nada real. Repetir `docker compose run --rm migrate` vuelve a aplicar migraciones y seed sin duplicar filas.

## M1: búsqueda real en YouTube

Requiere una clave de YouTube Data API v3 en `YOUTUBE_API_KEY` (variable de entorno del usuario de Windows o línea en `.env`). Sin clave, la búsqueda queda deshabilitada y no se inventan datos.

Desde la pantalla **Corridas** se lanza una búsqueda: idioma, consulta, ventana (0–7, 8–30 o 31–90 días) y número máximo de búsquedas. Cada búsqueda cuesta 100 unidades de cuota (ver `docs/DECISIONS.md`, D-22). El **consumo del día** aparece en **Configuración**.

Si se agota la cuota, la corrida queda en **Pausada por cuota**. Use el botón **Reanudar** al día siguiente: solo se ejecuta lo pendiente.

Para importar un archivo exportado con derecho de reutilización (JSON o CSV), use `POST /api/v1/imports/provider-file` con `license_confirmed: true`. Las filas válidas se guardan y las inválidas se devuelven con su motivo. Repetir la misma `idempotency_key` no duplica nada.

Los datos de YouTube caducan a los 29 días. La purga se lanza manualmente con `kind=purge` hasta que exista el planificador (M5).

## Qué funciona en M0

- Resumen con contadores; las métricas no habilitadas aparecen como «No habilitado», nunca como 0.
- Radar de oportunidades: búsqueda, filtros, orden, paginación en servidor y selección de hasta 8.
- Ficha de oportunidad con cinco pestañas (evidencia internacional, mercado español, producción IA, evaluación, fuente y auditoría).
- Comparador de 2 a 8 oportunidades con fuente y fecha en cada celda. No marca ganador.
- Videos sintéticos con antigüedad, conflicto de idioma y tipo ambiguo.
- Corridas DEMO en cola: la API responde 202 y el worker las completa sin red.
- Configuración, proveedores y capacidades condicionadas, con su motivo de bloqueo.

## Qué no funciona todavía (y por qué)

- **No hay análisis IA ni búsqueda real en español.** Son M2 y M3; el demo muestra los campos como datos sintéticos.
- **No hay scheduler automático.** Las búsquedas y la purga se lanzan a mano (M5 lo automatiza).
- **Las puntuaciones compuestas están bloqueadas.** Con `COMPLIANCE_MODE=restricted` ninguna variable de entorno las habilita; el desbloqueo exigirá un registro en `policy_approvals` (M4).
- **No hay exportación CSV/JSON.** Llega en M3.
- **No hay autenticación.** Está previsto como modo local; `APP_ENV=production` se rechaza hasta implementarla.

## Estructura

```
backend/   FastAPI, SQLAlchemy 2, Alembic, worker, tests (pytest)
frontend/  React + TypeScript + Vite, TanStack Query/Table, Vitest, Playwright
config/    research.yaml (parámetros editables; no son límites del proveedor)
docs/      progreso, decisiones, plan de pruebas
.github/   CI sin secretos
```

## Variables de entorno

Vea [.env.example](.env.example). Ninguna clave es necesaria para el demo. Los valores de claves nunca se muestran en la API ni en los logs; los logs redactan campos con `key`, `secret`, `token` o `password`.

## Solo es una prueba