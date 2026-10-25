"""Recomendación con compuertas (spec §3.8, §8.9). Puro y determinista.

Las compuertas no suman puntos: cada una bloquea una conclusión y da un motivo.
Ninguna regla convierte la falta de datos en un resultado favorable.
"""

from dataclasses import dataclass, field

FACELESS_OK = ("FACELESS_CONFIRMED", "FACELESS_LIKELY")
REPLICATION_OK = ("REPLICATED", "PROMISING")
DEMAND_OK = ("OBSERVED", "INDICATIVE")
MIN_QUERIES = 6


@dataclass(frozen=True)
class DecisionInput:
    replication: str | None
    spanish_decision: str | None
    demand: str | None
    queries_run: int
    confidence: str | None
    faceless: str | None
    complexity: int | None
    rights: str | None


@dataclass(frozen=True)
class Decision:
    recommendation: str
    gates: list[str] = field(default_factory=list)


def decide(i: DecisionInput) -> Decision:
    gates: list[str] = []
    if (
        i.spanish_decision is None
        or i.queries_run < MIN_QUERIES
        or i.spanish_decision == "INSUFFICIENT_EVIDENCE"
    ):
        gates.append("INSUFFICIENT_EVIDENCE")
    if i.demand in ("UNPROVEN", "NOT_OBSERVED"):
        gates.append("DEMAND_UNPROVEN")
    if i.rights == "HIGH":
        gates.append("HIGH_COPYRIGHT_RISK")
    if i.rights in (None, "UNKNOWN"):
        gates.append("RIGHTS_NOT_ASSESSED")
    if i.faceless in (None, "UNKNOWN"):
        gates.append("FACELESS_NOT_ASSESSED")
    if i.complexity is None:
        gates.append("COMPLEXITY_NOT_ASSESSED")

    if i.rights == "HIGH":
        return Decision("REJECT", gates)
    if i.spanish_decision == "CROWDED":
        return Decision("WATCHLIST", gates)
    if i.replication not in REPLICATION_OK:
        return Decision("MORE_RESEARCH", gates)
    if "INSUFFICIENT_EVIDENCE" in gates:
        return Decision("MORE_RESEARCH", gates)
    if "DEMAND_UNPROVEN" in gates:
        # Spec §3.6: sin demanda demostrada, un piloto de validación de demanda, no un lanzamiento.
        return Decision("VALIDATE_DEMAND_PILOT", gates)
    if gates:
        return Decision("MORE_RESEARCH", gates)

    ready = (
        i.spanish_decision == "POTENTIAL_GAP"
        and i.demand in DEMAND_OK
        and i.confidence in ("MEDIUM", "HIGH")
        and i.faceless in FACELESS_OK
        and i.complexity is not None
        and i.complexity <= 3
        and i.rights in ("LOW", "MEDIUM")
    )
    return Decision("READY_FOR_PILOT" if ready else "MORE_RESEARCH", gates)
