from dataclasses import dataclass

from app.core.config import Settings

CAPABILITIES: dict[str, str] = {
    "advanced_scores": "Puntuaciones compuestas (índices 0–100)",
    "derived_metrics": "Métricas derivadas de YouTube API (outliers, cohortes, replicación)",
    "extended_history": "Históricos extendidos más allá del plazo de retención",
    "vidiq_api": "Adaptador directo a vidIQ",
}


@dataclass(frozen=True)
class CapabilityDecision:
    capability: str
    label: str
    allowed: bool
    state: str
    reason: str


def decide(capability: str, settings: Settings) -> CapabilityDecision:
    """Compuerta de políticas de M0.

    En M0 el modo es siempre `restricted`, así que ninguna capacidad condicionada se habilita.
    Una variable de entorno como ADVANCED_ANALYTICS_ENABLED=true NO basta (spec §4.3, T17):
    el desbloqueo real exigirá un registro en `policy_approvals`, que llega con M4.
    """
    if capability not in CAPABILITIES:
        raise KeyError(f"Capacidad desconocida: {capability}")
    label = CAPABILITIES[capability]
    if settings.compliance_mode == "restricted":
        return CapabilityDecision(
            capability=capability,
            label=label,
            allowed=False,
            state="RESTRICTED",
            reason=(
                "COMPLIANCE_MODE=restricted: requiere aprobación registrada en policy_approvals."
            ),
        )
    raise NotImplementedError("Solo el modo restricted existe en M0.")


def all_decisions(settings: Settings) -> list[CapabilityDecision]:
    return [decide(name, settings) for name in CAPABILITIES]
