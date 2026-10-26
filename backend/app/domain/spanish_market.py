"""Reglas del mercado español (spec §3.6). Puras: sin I/O, fáciles de probar.

Principios:
- Ausencia de resultados NO es oportunidad ni baja saturación (T10).
- Un competidor cuenta como exacto solo si una persona lo confirmó (EXACT).
- Un video solo cuenta como español si su idioma verificado es "es".
"""

from dataclasses import dataclass

MIN_QUERIES = 6  # spec §3.6: >=6 consultas semánticas por oportunidad
MIN_QUERY_VARIANTS = 2  # >=2 variantes
EXACT_HIGH = 5  # competidores exactos confirmados para considerar saturación alta
# Parte mínima de los videos en español que una persona debe revisar para poder decir que la
# saturación es baja o media: con una revisión parcial, lo no revisado podría ser competencia.
MIN_REVIEW_SHARE = 0.8
DEMAND_STATES = ("OBSERVED", "INDICATIVE", "UNPROVEN", "NOT_OBSERVED")


@dataclass(frozen=True)
class SpanishCoverage:
    queries_run: int
    query_variants: int
    es_verified_videos: int
    reviewed_matches: int  # videos únicos en español revisados por una persona
    exact_matches: int  # videos únicos marcados como competidor exacto


@dataclass(frozen=True)
class SpanishAssessment:
    saturation_state: str
    demand_state: str
    entry_decision: str
    confidence: str
    reason_codes: list[str]


def review_share(c: SpanishCoverage) -> float | None:
    """Parte de los videos en español ya revisados (0 a 1). None si no hay videos."""
    if c.es_verified_videos <= 0:
        return None
    return min(1.0, c.reviewed_matches / c.es_verified_videos)


def saturation_state(
    c: SpanishCoverage, min_review_share: float = MIN_REVIEW_SHARE
) -> tuple[str, list[str]]:
    if c.queries_run < MIN_QUERIES or c.query_variants < MIN_QUERY_VARIANTS:
        return "UNKNOWN", ["ES_QUERY_COVERAGE_LOW"]
    if c.es_verified_videos == 0:
        return "UNKNOWN", ["ES_NO_VERIFIED_RESULTS"]
    if c.reviewed_matches == 0:
        return "UNKNOWN", ["ES_MATCH_NOT_REVIEWED"]
    if c.exact_matches >= EXACT_HIGH:
        return "HIGH", []  # seguir revisando solo puede sumar competidores: es una cota inferior
    share = review_share(c)
    if share is None or share < min_review_share:
        return "UNKNOWN", ["ES_REVIEW_COVERAGE_LOW"]
    if c.exact_matches >= 1:
        return "MEDIUM", []
    return "LOW", []


def demand_state(independent_signals: int) -> str:
    """Dos señales independientes para OBSERVED (spec §3.6). Sin señales: no demostrada."""
    if independent_signals >= 2:
        return "OBSERVED"
    if independent_signals == 1:
        return "INDICATIVE"
    return "UNPROVEN"


def assess(
    c: SpanishCoverage,
    independent_signals: int = 0,
    min_review_share: float = MIN_REVIEW_SHARE,
) -> SpanishAssessment:
    saturation, reasons = saturation_state(c, min_review_share)
    demand = demand_state(independent_signals)
    if c.queries_run < MIN_QUERIES:
        decision = "INSUFFICIENT_EVIDENCE"
    elif demand == "UNPROVEN":
        decision = "DEMAND_UNPROVEN"
        reasons = [*reasons, "ES_DEMAND_NOT_MEASURED"]
    elif saturation == "UNKNOWN":
        decision = "INSUFFICIENT_EVIDENCE"
    elif saturation == "HIGH":
        decision = "CROWDED"
    elif saturation == "MEDIUM":
        decision = "POTENTIAL_GAP" if demand in ("OBSERVED", "INDICATIVE") else "DEMAND_UNPROVEN"
    else:
        decision = "POTENTIAL_GAP" if demand in ("OBSERVED", "INDICATIVE") else "DEMAND_UNPROVEN"
    # Nunca se llega a GAP_CONFIRMED en M2: requiere la evidencia completa de M3.
    confidence = _confidence(c, saturation)
    return SpanishAssessment(saturation, demand, decision, confidence, reasons)


def _confidence(c: SpanishCoverage, saturation: str) -> str:
    if saturation == "UNKNOWN":
        return "INSUFFICIENT" if c.queries_run == 0 else "LOW"
    if c.reviewed_matches >= 10 and c.queries_run >= 10:
        return "MEDIUM"
    return "LOW"  # la confianza nunca sube solo por ausencia de resultados
