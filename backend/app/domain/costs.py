"""Modelo de costo por video (spec §3.7). Puro: sin precios inventados.

- Cada línea tiene cantidad y un precio por escenario (bajo, base, alto), escrito por una persona.
- Si falta el precio de una línea en un escenario, el total de ese escenario es NULL, no 0 (T15).
- Los totales son estimaciones y así se etiquetan.
"""

from dataclasses import dataclass

SCENARIOS = ("low", "base", "high")


@dataclass(frozen=True)
class CostLine:
    name: str
    unit: str
    quantity: float
    prices: dict[str, float | None]


@dataclass(frozen=True)
class CostResult:
    totals: dict[str, float | None]
    missing: dict[str, list[str]]


def planned_words(duration_minutes: float, words_per_minute: int) -> int:
    """Palabras del guion según duración y ritmo. Es información, no un costo."""
    return round(duration_minutes * words_per_minute)


def compute(lines: list[CostLine]) -> CostResult:
    totals: dict[str, float | None] = {}
    missing: dict[str, list[str]] = {}
    for scenario in SCENARIOS:
        gaps: list[str] = []
        total = 0.0
        for line in lines:
            price = line.prices.get(scenario)
            if price is None:
                gaps.append(line.name)
                continue
            total += line.quantity * price
        missing[scenario] = gaps
        totals[scenario] = None if gaps else round(total, 2)
    return CostResult(totals=totals, missing=missing)
