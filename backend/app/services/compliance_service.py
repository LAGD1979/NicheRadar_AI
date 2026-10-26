from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m

CAPABILITIES: dict[str, str] = {
    "advanced_scores": "Puntuaciones compuestas (índices 0–100)",
    "derived_metrics": "Métricas derivadas de YouTube API (outliers, cohortes, replicación)",
    "extended_history": "Históricos extendidos más allá del plazo de retención",
    "vidiq_api": "Adaptador directo a vidIQ",
    "google_trends": "Google Trends (índice relativo, vía HasData)",
}
RESTRICTED_REASON = (
    "COMPLIANCE_MODE=restricted: requiere aprobación registrada en policy_approvals."
)


@dataclass(frozen=True)
class CapabilityDecision:
    capability: str
    label: str
    allowed: bool
    state: str
    reason: str
    approval_ref: str | None = None


def _blocked(capability: str, reason: str) -> CapabilityDecision:
    return CapabilityDecision(
        capability=capability,
        label=CAPABILITIES[capability],
        allowed=False,
        state="RESTRICTED",
        reason=reason,
    )


def active_approval(session: Session, capability: str, now: datetime) -> m.PolicyApproval | None:
    """Aprobación vigente: activa, ya en vigor, no vencida. Caducada o revocada no cuenta (T18)."""
    rows = session.scalars(
        select(m.PolicyApproval).where(
            m.PolicyApproval.capability == capability,
            m.PolicyApproval.status == "ACTIVE",
        )
    ).all()
    for approval in rows:
        if approval.effective_at is not None and approval.effective_at > now:
            continue
        if approval.expires_at is None or approval.expires_at <= now:
            continue
        return approval
    return None


def decide(
    capability: str,
    settings: Settings,
    session: Session | None = None,
    now: datetime | None = None,
) -> CapabilityDecision:
    """Compuerta de políticas (spec §4.3, T17, T18).

    Se habilita solo si se cumplen las tres condiciones a la vez:
    1. COMPLIANCE_MODE=approved_scope (en `restricted` nunca se habilita nada).
    2. ADVANCED_ANALYTICS_ENABLED=true.
    3. Un registro activo y vigente en policy_approvals para la capacidad.
    Una variable de entorno sola no basta.
    """
    if capability not in CAPABILITIES:
        raise KeyError(f"Capacidad desconocida: {capability}")
    if settings.compliance_mode == "restricted":
        return _blocked(capability, RESTRICTED_REASON)
    if not settings.advanced_analytics_enabled:
        return _blocked(capability, "ADVANCED_ANALYTICS_ENABLED=false.")
    if session is None:
        return _blocked(capability, "Sin consulta a policy_approvals: no se puede verificar.")
    approval = active_approval(session, capability, now or datetime.now(UTC))
    if approval is None:
        return _blocked(
            capability, "Sin aprobación vigente en policy_approvals (ausente, caducada o revocada)"
        )
    return CapabilityDecision(
        capability=capability,
        label=CAPABILITIES[capability],
        allowed=True,
        state="AVAILABLE",
        reason=(
            f"Aprobación {approval.approval_ref or approval.id} "
            f"vigente hasta {approval.expires_at}."
        ),
        approval_ref=approval.approval_ref,
    )


def all_decisions(
    settings: Settings, session: Session | None = None, now: datetime | None = None
) -> list[CapabilityDecision]:
    return [decide(name, settings, session, now) for name in CAPABILITIES]
