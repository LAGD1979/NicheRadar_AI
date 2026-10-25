# Progreso de implementación

Última actualización: 2026-10-25. Para retomar el trabajo, lea primero `docs/HANDOFF.md`.

## Hitos

| Hito | Estado | Notas |
|---|---|---|
| **M0 — cimientos y demo sintético** | ✔ Completado (commit `b8762f9`) | Compose, API, worker, migraciones, seed, dashboard, E2E, CI. |
| **M1 — ingesta oficial, cuota, importación** | ✔ Completado (commit `29ce8bc`) | Búsqueda real probada. Ver «Límites» de M1 en el historial. |
| **M2 — mercado español y planes de búsqueda** | ✔ Completado con límites (commit `349fcee`) | Validación real probada una vez. IA probada en vivo con OpenAI (D-55) y Anthropic (D-56). Sin fuentes de demanda. |
| **M3 — factibilidad, decisiones, comparador, export** | ✔ Completado con límites (commit `86c3ae8`) | Costos, factibilidad, recomendación con compuertas, export CSV/JSON. Sin watchlist (Seguimiento). |
| **M4 — analítica avanzada (condicional)** | ◐ Construido y abierto en este equipo (commits `fbc07d0`, `ad9bcdb`) | Compuerta de tres condiciones (D-48). El responsable registró las aprobaciones (D-54); no son una autorización de YouTube. Los índices siguen en NULL por falta de histórico licenciado. |
| M5 — radar continuo | — pendiente | Scheduler, purga automática, alertas, watchlist. |

Documentación: manuales de uso y técnico en `frontend/public/manual/` (commit `ea5195e`); traspaso en `docs/HANDOFF.md`.

## M3: costos, factibilidad, recomendación y exportación

- **Costos** (`domain/costs.py`): precios por escenario escritos por una persona; un precio faltante deja el total en NULL (T15). Versionado en `cost_models`.
- **Factibilidad**: valoración humana con motivo obligatorio (faceless y riesgo de derechos).
- **Recomendación con compuertas** (`domain/decision.py`): `REJECT`, `WATCHLIST`, `MORE_RESEARCH`, `VALIDATE_DEMAND_PILOT` y `READY_FOR_PILOT`, con sus motivos. Se recalcula en cada versión de evaluación (`services/evaluation_service.py`).
- **Exportación** CSV y JSON con los filtros activos, neutralización de fórmulas (T20) y advertencia de caducidad.
- **Comparador**: recomendación, compuertas y minutos humanos por video.
- **Interfaz**: panel de producción con costo y valoración en la ficha; contadores de «listas para piloto» y «validar demanda» en Resumen; enlaces de exportación en el radar.

Verificación de M3: **194 pruebas backend** (160 al cierre de M2 + 34 de M3), lint y tipos limpios, **15 pruebas frontend**, **7 E2E** de M0 (1 omitido), migración 0004 aplicada sobre la base de la demo.

Limitaciones de M3:
- **`READY_FOR_PILOT` aparece para `syn-opp-01`** porque su fixture sintético declara demanda indicativa (D-45). No es una señal real.
- **Las recomendaciones del fixture** se muestran tal cual hasta que hay una evaluación nueva (D-46).
- **P4 y P5 (IA de factibilidad)** no se implementaron: la factibilidad la valora una persona. Anthropic se probó en vivo después (D-56).
- **Sin watchlist** (Seguimiento) ni **sin pantalla de política** nueva: se mantiene la de Configuración.

## M2: qué se construyó

- **Oportunidades y anotaciones:** un video confirmado (LONG o SHORT) se asigna a nicho + formato. Varias anotaciones forman un solo grupo (T08). Mismo formato en otro nicho es otra oportunidad (T09).
- **Planes de búsqueda en español:** escritos por una persona o generados por IA. Validados por esquema, sin URLs y con fuentes que existen (T13). Se aprueban y quedan bloqueados; aprobar otro reemplaza el anterior.
- **Validación en español:** búsquedas con `relevanceLanguage=es` por ventanas. Cuenta como español solo lo verificado por idioma declarado. Crea versiones nuevas de la evaluación.
- **Revisión humana:** cada competidor se marca como exacto, cercano, genérico o falso positivo. Solo los exactos cuentan para la saturación. Cada revisión recalcula el estado.
- **Reglas puras** (`domain/spanish_market.py`): cobertura mínima, saturación, demanda y decisión, con las pruebas de T10 y T11.
- **Interfaz:** pestaña «Mercado español» con planes, aprobación, validación, revisión de competidores y cobertura.

## Verificación de M2

| Comprobación | Resultado |
|---|---|
| Backend: pruebas | **160 pasan** (117 de M1 + 43 nuevas) |
| Backend: ruff y mypy | **sin errores** |
| Frontend: eslint, tsc, vitest (15), build | **sin errores** |
| E2E de M0 | **7 pasan, 1 omitido** |
| Migración 0003 sobre la base de la demo | **correcta** |
| **Validación real en español** (2 búsquedas, 1 ventana) | **PARTIAL** por presupuesto: 44 videos verificados como español, 0 revisados, decisión `INSUFFICIENT_EVIDENCE` |
| Revisión de un competidor | **recalcula** la evaluación (versión nueva) y actualiza contadores |
| IA sin configurar | **409 `AI_NOT_CONFIGURED`** |
| Clave en logs | **no aparece** |

Datos reales en la base: el video real «Stalingrado: la batalla que cambió…» se anotó a `syn-opp-06` (nicho 01 × formato 02), que antes no tenía evaluación. Esa oportunidad ahora mezcla datos sintéticos (su evidencia de origen) con datos reales. Conviene eliminarla antes de una demo.

## Criterio de aceptación de M2 (§13)

- [x] Taxonomía nicho + formato, oportunidad y etiquetas con evidencia.
- [x] Proveedor de IA tipado con validación de salida (P2).
- [x] Planes de búsqueda en español editables y aprobables.
- [x] Búsqueda en español con verificación de idioma.
- [x] Comparación entre formato exacto y adyacente (solo `EXACT` cuenta).
- [x] Estados de saturación y demanda `UNKNOWN` seguros.
- [~] Pipeline desde video en otro idioma hasta plan español y tabla de competencia: probado con datos reales; el plan de IA se generó en vivo con OpenAI y Anthropic (2026-10-25), pero aún no se ha encadenado con una validación completa.
- [ ] Revisión humana de muestras (30–50 videos, §13.3): no hay conjunto etiquetado todavía.

## Límites conocidos

- **Sin fuentes de demanda**: ninguna oportunidad pasa de `DEMAND_UNPROVEN` (D-35). Es la limitación más importante de M2.
- **IA probada en vivo con un plan por proveedor** (OpenAI `gpt-4.1-mini` y Anthropic `claude-haiku-5-5`, 2026-10-25; D-55 y D-56). No se probaron reintentos, modelos de razonamiento ni la calidad de las frases.
- **Sin revisión humana masiva**: el conjunto de 30–50 videos de §13.3 no existe todavía; la precisión por idioma no se ha medido.
- **Espejos (T12)**: no se detecta que varios canales sean del mismo creador. Pendiente.
- **Datos mezclados**: ver la nota de `syn-opp-06` arriba.
- **Banner DEMO**: sigue diciendo «DATOS SINTÉTICOS · DEMO» aunque haya datos reales (ver M1).
- **Sin autenticación**: la API acepta peticiones desde `127.0.0.1` sin login.

## Estado de verificación actual

230 pruebas de backend, 15 de frontend y 7 E2E pasando (1 omitido a propósito). Detalle de comandos en `docs/HANDOFF.md`.

## Siguiente paso

Las dos cosas que más limitan el radar: una fuente de señales de demanda en español (con licencia) y una prueba real de la IA con clave. En paralelo, iniciar M5 (scheduler, purga programada, watchlist). Pendientes completos: `docs/HANDOFF.md` §7.
