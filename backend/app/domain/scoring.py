"""Índices orientativos (spec §3.8, §10). Solo se usan con aprobación vigente (compuerta M4).

Reglas:
- Cada dimensión es un cociente entre 0 y 1, o None si falta el dato. None nunca se trata como 0.
- Un subíndice solo existe si todas sus dimensiones tienen dato; si no, es None.
- El índice integrado solo existe si los tres subíndices existen. Así una dimensión crítica
  ausente deja el resultado en NULL (spec §3.8, §14).
- Los pesos y las reglas de transformación tienen versión: `FORMULA_VERSION`.
"""

from dataclasses import dataclass

FORMULA_VERSION = "score-v1"

INTERNATIONAL_WEIGHTS: dict[str, float] = {
    "traccion": 35,
    "replicabilidad": 40,
    "resiliencia_temporal": 15,
    "diversidad_independiente": 10,
}
SPANISH_WEIGHTS: dict[str, float] = {
    "oferta_abordable": 35,
    "demanda_observable": 25,
    "exito_accesible": 25,
    "diferenciacion": 15,
}
OPERATIONAL_WEIGHTS: dict[str, float] = {
    "automatizacion": 35,
    "costos": 25,
    "derechos_originalidad": 25,
    "mantenibilidad": 15,
}
INTEGRATED_WEIGHTS: dict[str, float] = {"international": 35, "spanish": 40, "operational": 25}

Ratios = dict[str, float | None]


@dataclass(frozen=True)
class Subindex:
    value: float | None
    missing: list[str]


def subindex(weights: dict[str, float], ratios: Ratios) -> Subindex:
    missing = [name for name in weights if ratios.get(name) is None]
    if missing:
        return Subindex(None, missing)
    total_weight = 0.0
    weighted = 0.0
    for name, weight in weights.items():
        ratio = ratios[name]
        if ratio is None:  # ya filtrado arriba; se repite para el tipo
            return Subindex(None, [name])
        total_weight += weight
        weighted += weight * _clamp(ratio)
    return Subindex(round(100 * weighted / total_weight, 2), [])


def integrated(parts: dict[str, float | None]) -> Subindex:
    missing = [name for name in INTEGRATED_WEIGHTS if parts.get(name) is None]
    if missing:
        return Subindex(None, missing)
    total_weight = 0.0
    weighted = 0.0
    for name, weight in INTEGRATED_WEIGHTS.items():
        value = parts[name]
        if value is None:
            return Subindex(None, [name])
        total_weight += weight
        weighted += weight * value
    return Subindex(round(weighted / total_weight, 2), [])


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def replication_ratio(state: str | None) -> float | None:
    return {"REPLICATED": 1.0, "PROMISING": 0.6, "SINGLE_OUTLIER": 0.2}.get(state or "")


def channels_ratio(count: int | None) -> float | None:
    """Canales independientes: 3 o más es el umbral de replicación (spec §3.4)."""
    if count is None:
        return None
    return _clamp(count / 3)


def saturation_ratio(state: str | None) -> float | None:
    """Menor saturación, mayor puntuación. Desconocido no puntúa (T10)."""
    return {"LOW": 1.0, "MEDIUM": 0.6, "HIGH": 0.2}.get(state or "")


def demand_ratio(state: str | None) -> float | None:
    """Solo las señales observadas o indicativas puntúan; «no demostrada» no es cero."""
    return {"OBSERVED": 1.0, "INDICATIVE": 0.6}.get(state or "")


def complexity_ratio(complexity: int | None) -> float | None:
    """Más simple, mejor: 1 da 1,0 y 5 da 0,0."""
    if complexity is None or not 1 <= complexity <= 5:
        return None
    return (5 - complexity) / 4


def rights_ratio(risk: str | None) -> float | None:
    return {"LOW": 1.0, "MEDIUM": 0.5, "HIGH": 0.0}.get(risk or "")


def differentiation_ratio(level: str | None) -> float | None:
    """Diferenciación editorial: la valora una persona. Sin valoración no hay puntuación."""
    return {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.2}.get(level or "")


def maintenance_ratio(level: str | None) -> float | None:
    """Menos esfuerzo de mantener al día, mejor. Sin valoración no hay puntuación."""
    return {"LOW_EFFORT": 1.0, "MODERATE": 0.6, "HIGH_EFFORT": 0.2}.get(level or "")


def observed_ratio(value: object) -> float | None:
    """Ya viene medida (0 a 1) o es None; nunca se completa con un valor por defecto."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return _clamp(float(value))


def cost_ratio(
    usd: float | None, cohort_min: float | None, cohort_max: float | None
) -> float | None:
    """Normalización dentro del estrato: el costo más bajo puntúa 1. Sin estrato, no hay índice."""
    if usd is None or cohort_min is None or cohort_max is None:
        return None
    if cohort_max == cohort_min:
        return 1.0
    return _clamp(1 - (usd - cohort_min) / (cohort_max - cohort_min))


def rank(items: list[tuple[str, float | None]]) -> list[tuple[str, float | None]]:
    """Orden estable: mayor índice primero; los NULL al final; empates por ID."""
    with_value = sorted((i for i in items if i[1] is not None), key=lambda i: (-i[1], i[0]))  # type: ignore[operator]
    without = sorted((i for i in items if i[1] is None), key=lambda i: i[0])
    return [*with_value, *without]
