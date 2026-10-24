# NicheRadar AI — Instrucciones permanentes para Claude Code

> Proyecto: sistema automatizado de investigación de nichos YouTube internacionales, validación de demanda/saturación en español y dashboard de oportunidades comparables.
> Documento normativo funcional: `ESPECIFICACION_NICHERADAR_AI.md` en la raíz.
> README operativo: `INICIO_CON_CLAUDE_CODE.md`.

## Misión

Implementar **código funcional**, paso a paso, acorde con la especificación. No efectuar una investigación real de nichos durante el desarrollo inicial. Comenzar con datos sintéticos rotulados DEMO y pruebas; acceso real a fuentes solo cuando existan credenciales/permiso y el usuario lo solicite.

El usuario final necesita: (1) descubrir señales recientes en otros idiomas, (2) validar repetibilidad, (3) evaluar específicamente saturación y demanda en español, (4) estimar complejidad faceless con IA, (5) comparar y elegir oportunidades en un dashboard. La **unidad de análisis es nicho + formato**, no solo keywords.

## Forma de trabajar

1. Al iniciar, leer primero este archivo, luego el índice de secciones del documento principal y las partes relevantes al hito actual. No releer el documento íntegro en cada cambio menor.
2. Inspeccionar el repo. Si está vacío, crear estructura descrita en §12. Evitar frameworks adicionales que no aporten valor.
3. Mantener `docs/IMPLEMENTATION_PROGRESS.md` con estado de hitos, decisiones, pruebas, bloqueos externos y siguiente paso.
4. Implementar por M0 → M1 → M2 → M3 → M4 (condicional) → M5. Antes de iniciar el siguiente, completar pruebas del hito anterior y registrar su resultado.
5. Ante ambigüedad no bloqueante, seguir los defaults §17 y anotar la interpretación en `docs/DECISIONS.md`.
6. Entregar cambios pequeños y verificables, con tests y migraciones; no dejar stubs que fingen éxito.
7. Ejecutar comandos reales de test y arranque cuando el entorno lo permita; si faltan Docker/credenciales, registrar con precisión qué pudo comprobarse.
8. Mantener la aplicación usable incluso cuando proveedores opcionales estén desconectados: `/demo` o dataset sintético, proveedor oficial cuando se habilite, importación CSV/JSON licenciada.

## Arquitectura decidida

- Backend: Python + FastAPI + SQLAlchemy/Pydantic + Alembic.
- DB: PostgreSQL en Compose; SQLite opcional solo para fixtures/tests.
- UI: React + TypeScript + Vite + TanStack Table/Query + Recharts + componentes accesibles.
- Worker con cola persistente, scheduler y locks transaccionales para no duplicar tareas; no ejecutar trabajos largos dentro de requests web.
- Integraciones mediante puertos/adaptadores tipados; YouTube API oficial obligatorio, importador permitido; vidIQ externo opcional y **no asumido** disponible desde Claude Code.
- Solo módulos de IA que consuman evidencia lícita, devuelvan JSON estructurado y citen `source_id` para hechos.
- Dashboard con vistas `Resumen`, `Videos`, `Oportunidades`, `Detalle`, `Comparador`, `Corridas`, `Seguimiento`, `Configuración`.

## Prohibiciones críticas

- NO inventar estadísticas, nichos reales, canales, enlaces, resultados de investigación, API keys o precios de IA.
- NO hacer scraping no autorizado ni prometer que el conector vidIQ de ChatGPT se puede utilizar automáticamente en Claude Code.
- NO calcular o exponer scores avanzados ni almacenar datos de terceros por más de los plazos permitidos por YouTube si faltan las condiciones/autorizaciones aplicables. `COMPLIANCE_MODE=restricted` y `ADVANCED_ANALYTICS_ENABLED=false` por defecto; obedecer `policy_approvals` y no permitir bypass desde UI o solo por variable de entorno.
- NO asumir que la falta de resultados en español indica oportunidad o poca saturación. En evidencia insuficiente, `UNKNOWN`.
- NO confundir idioma de vídeo y país; LONG/SHORT separados; no afirmar visual faceless a partir de una miniatura o título.
- NO fusionar métricas oficiales, proveedor y estimaciones de IA sin procedencia explícita.
- NO tratar valores `NULL` como 0 o score nulo como 0; no sumar ponderaciones sin evidencia.
- NO presentar contenido masivo repetitivo o traducción casi literal de competidores como pipeline ideal de producción; propuesta original y control de derechos.
- NO crear tareas/alertas reales fuera del sistema en el equipo del usuario salvo que se implementen y activen explícitamente allí.

## Contratos de calidad

- Todos los registros externos: ID, proveedor, `observed_at`, vigencia y `run_id`.
- Import idempotente por `external_id`, `run_id` y query; errores parciales expresos.
- Si falta autorización para análisis completo, `PARTIAL_POLICY_RESTRICTED` y explicar la limitación; no falsear shortlist validada.
- Pydantic de inputs/outputs y tests de estados/indicadores; SQL injection/CSV formula injection/SSRF protegidos.
- 25 casos T01–T25 del documento deben pasar antes de declarar terminado el MVP.
- Comparador de 2–8 oportunidades, con evidencia lado a lado, filtros y export CSV/JSON.
- Debe funcionar modo DEMO totalmente desconectado de servicios reales.

## Orden inicial de trabajo — primera sesión

1. Crear estructura de archivos y base monorepo siguiendo §12.
2. Compose: `db`, `api`, `worker`, `frontend` (y scheduler, si separado). Health checks.
3. Modelos mínimos de M0 y primeras migraciones.
4. Seed de fixtures sintéticos; rutas API `/health/*`, `/config/public`, `/opportunities`, `/opportunities/:id`, `/compare` en modo demo.
5. Frontend inicial: layout, radar tabla, ficha y comparador con cuatro oportunidades **DEMO** y nulos correctos.
6. Tests unitarios/integración/E2E mínimo de la demo.
7. README con comandos que verdaderamente funcionen; docs/IMPLEMENTATION_PROGRESS.md.
8. Tras mostrar M0 funcional, implementar YouTubeOfficialProvider, cuotas y workers M1.

## Criterios de entrega por sesión

Al finalizar una sesión, resumir archivos creados/modificados, funcionalidades que realmente operan, tests ejecutados y resultados, bloqueos externos y siguiente paso concreto. No confundir especificación o maquetas estáticas con integración real funcionando.
