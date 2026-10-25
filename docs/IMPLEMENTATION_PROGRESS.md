# Progreso de implementación

Última actualización: 2026-10-25.

## Hitos

| Hito | Estado | Notas |
|---|---|---|
| **M0 — cimientos y demo sintético** | ✔ Completado (commit `b8762f9`) | Compose, API, worker, migraciones, seed, dashboard, E2E, CI. |
| **M1 — ingesta oficial, cuota, importación** | ✔ Completado (commit `29ce8bc`) | Búsqueda real probada. Ver «Límites» de M1 en el historial. |
| **M2 — mercado español y planes de búsqueda** | ✔ Completado con límites (sin commit) | Validación real probada una vez. IA sin probar en vivo. Sin fuentes de demanda. |
| M3 — factibilidad, decisiones, comparador completo, export | — pendiente | Export CSV/JSON, watchlist, costos. |
| M4 — analítica avanzada (condicional) | — bloqueado | Requiere `policy_approvals` documentado. |
| M5 — radar continuo | — pendiente | Scheduler, purga automática, alertas. |

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
- [~] Pipeline desde video en otro idioma hasta plan español y tabla de competencia: probado con datos reales, pero el plan de IA no se ha ejecutado en vivo.
- [ ] Revisión humana de muestras (30–50 videos, §13.3): no hay conjunto etiquetado todavía.

## Límites conocidos

- **Sin fuentes de demanda**: ninguna oportunidad pasa de `DEMAND_UNPROVEN` (D-35). Es la limitación más importante de M2.
- **La IA no se ha probado en vivo**: no hay clave ni modelo de Anthropic configurados. El cliente sigue el contrato de la API, pero no se ha ejecutado.
- **Sin revisión humana masiva**: el conjunto de 30–50 videos de §13.3 no existe todavía; la precisión por idioma no se ha medido.
- **Espejos (T12)**: no se detecta que varios canales sean del mismo creador. Pendiente.
- **Datos mezclados**: ver la nota de `syn-opp-06` arriba.
- **Banner DEMO**: sigue diciendo «DATOS SINTÉTICOS · DEMO» aunque haya datos reales (ver M1).
- **Sin autenticación**: la API acepta peticiones desde `127.0.0.1` sin login.
- **Git**: M2 no tiene commit todavía.

## Siguiente paso

Decidir si M2 se commitea. Después, las dos cosas que más limitan el radar: una fuente de señales de demanda en español (con licencia) y una prueba real de la IA con clave de Anthropic.
