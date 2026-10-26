"""Éxito accesible a canales pequeños en el mercado español (spec §10.4).

Función pura. Mide, entre los competidores directos que una persona marcó como «exactos», qué
parte son canales pequeños con vistas altas. Es evidencia observada en una muestra de búsquedas,
no un censo de competidores, y no se compara contra un estrato temporal (pendiente).

Reglas de honestidad:
- Sin competidores exactos no hay medida: no se puntúa como cero (T10).
- Con menos de `min_sample` competidores con vistas y suscriptores conocidos, tampoco.
- Un valor faltante nunca cuenta como cero ni como éxito.
"""

from dataclasses import dataclass
from typing import Any

RULE_VERSION = "small-access-v1"


@dataclass(frozen=True)
class ExactCompetitor:
    video_id: str
    channel_id: str
    view_count: int | None
    subscriber_count: int | None


def assess(
    competitors: list[ExactCompetitor],
    *,
    success_min_views: int = 50_000,
    small_max_subscribers: int = 50_000,
    min_sample: int = 3,
) -> dict[str, Any]:
    unique: dict[str, ExactCompetitor] = {}
    for item in competitors:
        unique.setdefault(item.video_id, item)
    evaluable = [
        c for c in unique.values() if c.view_count is not None and c.subscriber_count is not None
    ]
    small = [c for c in evaluable if (c.subscriber_count or 0) <= small_max_subscribers]
    successes = [c for c in small if (c.view_count or 0) >= success_min_views]

    if not unique:
        state, ratio = "NO_EXACT_MATCHES", None
    elif len(evaluable) < min_sample:
        state, ratio = "INSUFFICIENT_SAMPLE", None
    else:
        state, ratio = "OBSERVED", round(len(successes) / len(evaluable), 3)

    return {
        "state": state,
        "ratio": ratio,
        "exact_competitors": len(unique),
        "evaluated": len(evaluable),
        "small_channels": len({c.channel_id for c in small}),
        "small_channel_successes": len(successes),
        "min_sample": min_sample,
        "success_min_views": success_min_views,
        "small_max_subscribers": small_max_subscribers,
        "rule_version": RULE_VERSION,
    }
