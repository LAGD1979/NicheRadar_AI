# Cómo utilizar el paquete NicheRadar AI en Claude Code

## 1. Contenido

- `ESPECIFICACION_NICHERADAR_AI.md`: contrato funcional y técnico integral, desde la metodología internacional y saturación en español hasta dashboard, arquitectura, APIs, reglas de calidad y aceptación.
- `CLAUDE.md`: instrucciones persistentes para que Claude Code implemente el proyecto por hitos sin inventar evidencia o romper normas de proveedores.
- `INICIO_CON_CLAUDE_CODE.md`: esta guía de arranque.

Este paquete es una **especificación**, no un programa terminado, y **no contiene resultados de la investigación de nichos**.

## 2. Preparación

1. Descomprime el paquete en una carpeta de trabajo nueva (por ejemplo, `nicheradar-ai`).
2. Instala Claude Code siguiendo las instrucciones oficiales del proveedor, junto con Docker Desktop y Git si los vas a utilizar.
3. Abre una terminal en la carpeta que contiene `CLAUDE.md`.
4. Ejecuta `claude` para iniciar Claude Code. Lee automáticamente el `CLAUDE.md` de la carpeta según la documentación de Claude.

No es necesario obtener una API key de YouTube antes del primer hito. El MVP inicial debe funcionar con fixtures completamente sintéticos.

## 3. Prompt inicial recomendado (copiar en Claude Code)

```text
Quiero que implementes NicheRadar AI a partir de ESPECIFICACION_NICHERADAR_AI.md y las reglas permanentes de CLAUDE.md.

Comienza por el Hito M0 y después M1, pero realiza cambios verificables por fases; no intentes implementar todo de golpe. En cada hito escribe código real, migraciones, tests, interfaz y comandos de arranque. Empieza con modo DEMO y datos sintéticos, sin consultar datos de YouTube ni servicios de pago.

El dashboard debe tener un radar de oportunidades, ficha de cada nicho+formato, filtros y comparador lado a lado de hasta ocho oportunidades, distinguiendo claramente éxito internacional, saturación/demanda en español y factibilidad de pipeline faceless.

Usa decisiones técnicas de §4, esquema §6, backend §7, pantallas §8, tareas §10, estructura §12 y criterios de aceptación §14–16. Prioriza que `docker compose up --build` levante el proyecto y que las pruebas pasen.

Mantén actualizado docs/IMPLEMENTATION_PROGRESS.md. No declares como terminado nada que no hayas probado. Si un conector requiere permisos o credenciales, deja el adaptador listo, deshabilitado y documentado.
```

## 4. Siguientes sesiones

**Para M2 (análisis semántico y español):**

```text
Continúa NicheRadar AI desde docs/IMPLEMENTATION_PROGRESS.md. Implementa M2: taxonomía nicho+formato, fuentes/evidencias, prompts tipados, plan de búsquedas españolas y análisis de competencia/demanda. Sigue las restricciones legales y reglas de desconocidos. Añade tests T04, T08–T14 y verificaciones de datos demo. No hacer búsquedas reales sin configuración y autorización.
```

**Para M3 (dashboard completo):**

```text
Continúa NicheRadar AI y completa M3: dashboard y comparador de 2 a 8 oportunidades, análisis de producción faceless, escenarios de costos parametrizados, decisiones con gates, filtros, exportaciones y estados de error. Implementa las vistas de §8 y tests E2E. Verifica responsive desktop/móvil y fuentes verificables.
```

**Para M4 (solo cuando el proyecto tenga fuente/licencia/habilitación):**

```text
Evalúa primero SOURCE_POLICY_MATRIX.md y policy_approvals. Si el entorno tiene permisos suficientes, implementa M4: scoring derivado, cohorts, outlier, replicabilidad e históricos conforme a §§5,9; si no, mantén bloqueado y mejora visualización permitida sin bypass. Agrega pruebas que garanticen el bloqueo de métricas restringidas.
```

**Para M5 (radar automático):**

```text
Implementa M5: programador de investigaciones, workers persistentes, reintentos, límites de cuotas y costos, refresco y purga, watchlist, alertas in-app y observabilidad. Ejecuta pruebas de reinicio, idempotencia y datos vencidos. No declares autosuficiente una investigación si faltan fuentes o cobertura en español.
```

## 5. Credenciales necesarias para operaciones reales (posteriores a demo)

- Una clave de proyecto autorizada de YouTube Data API para consultar metadatos públicos.
- Credencial y permiso de un LLM (Anthropic u OpenAI) para analizar metadatos y generar planes de búsqueda/producción.
- Un proveedor con acceso autorizado para hallar outliers e históricos/indicadores avanzados (o un mecanismo de importación con licencia). **La integración vidIQ existente en ChatGPT no es automáticamente un acceso desde Claude Code**.
- Para crear/guardar scores derivados de YouTube API Data fuera del régimen básico, verificar el procedimiento vigente de aceptación/habilitación previsto en políticas oficiales y guardar su constancia en la plataforma. Si no está, usar modo restringido.

## 6. Qué considerar una entrega real

El primer éxito no es un documento adicional ni un mockup visual. Debe existir una aplicación que se inicie localmente, muestre cuatro o más oportunidades sintéticas, permita navegar/filtrar/comparar, y muestre cómo se validará la saturación en español. Después integrar datos externos. Los resultados de investigación reales solo tienen sentido cuando las fuentes funcionen y los límites legales/metodológicos estén resueltos.

## 7. Referencias oficiales

- YouTube API: https://developers.google.com/youtube/data/getting-started
- Guía de políticas: https://developers.google.com/youtube/terms/developer-policies-guide
- Métricas derivadas: https://developers.google.com/youtube/terms/derived-metrics-policy
- Claude Code y CLAUDE.md: https://support.claude.com/en/articles/14553240-give-claude-context-claude-md-and-better-prompts
