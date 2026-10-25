"""M4 contra PostgreSQL: la compuerta no se abre sin un registro vigente (T17, T18)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models as m


def _approval(
    *,
    approval_id: str = "appr-1",
    capability: str = "advanced_scores",
    status: str = "ACTIVE",
    expires_in_days: int = 30,
) -> m.PolicyApproval:
    now = datetime.now(UTC)
    return m.PolicyApproval(
        id=approval_id,
        provider="youtube_official",
        capability=capability,
        scope="todas las oportunidades de la demo",
        status=status,
        approval_ref="DOC-REVISION-DERIVADAS-001",
        reviewed_by="local_owner",
        effective_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=expires_in_days),
        notes="Aprobación de prueba: no es una autorización real de YouTube.",
    )


@pytest.fixture
def mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Cambia el modo de cumplimiento y la variable de analítica avanzada para una prueba."""

    def apply(compliance: str, advanced: bool) -> None:
        monkeypatch.setenv("COMPLIANCE_MODE", compliance)
        monkeypatch.setenv("ADVANCED_ANALYTICS_ENABLED", "true" if advanced else "false")
        get_settings.cache_clear()

    yield apply
    monkeypatch.delenv("COMPLIANCE_MODE", raising=False)
    monkeypatch.delenv("ADVANCED_ANALYTICS_ENABLED", raising=False)
    get_settings.cache_clear()


def test_restricted_mode_stays_closed_even_with_a_valid_approval(
    client: TestClient, seeded_db: Session, mode: Any
) -> None:
    seeded_db.add(_approval())
    seeded_db.commit()
    mode("restricted", True)
    assert client.post("/api/v1/opportunities/syn-opp-01/scores").status_code == 403
    assert client.get("/api/v1/opportunities/syn-opp-01/scores/detail").status_code == 403


def test_env_flag_without_approval_does_not_open_the_gate(client: TestClient, mode: Any) -> None:
    mode("approved_scope", True)
    response = client.post("/api/v1/opportunities/syn-opp-01/scores")
    assert response.status_code == 403
    assert response.json()["code"] == "POLICY_RESTRICTED"


def test_approval_without_advanced_flag_stays_closed(
    client: TestClient, seeded_db: Session, mode: Any
) -> None:
    seeded_db.add(_approval())
    seeded_db.commit()
    mode("approved_scope", False)
    assert client.post("/api/v1/opportunities/syn-opp-01/scores").status_code == 403


@pytest.mark.parametrize(
    "kwargs",
    [
        {"approval_id": "appr-expired", "expires_in_days": -1},  # T18: caducada
        {"approval_id": "appr-revoked", "status": "REVOKED"},  # revocada
        {"approval_id": "appr-other", "capability": "derived_metrics"},  # otra capacidad
    ],
)
def test_expired_revoked_or_other_capability_stays_closed(
    client: TestClient, seeded_db: Session, mode: Any, kwargs: dict[str, Any]
) -> None:
    seeded_db.add(_approval(**kwargs))
    seeded_db.commit()
    mode("approved_scope", True)
    assert client.post("/api/v1/opportunities/syn-opp-01/scores").status_code == 403


def test_valid_approval_opens_the_gate_and_null_dimensions_stay_null(
    client: TestClient, seeded_db: Session, mode: Any
) -> None:
    seeded_db.add(_approval())
    seeded_db.commit()
    mode("approved_scope", True)
    response = client.post("/api/v1/opportunities/syn-opp-01/scores")
    assert response.status_code == 201
    detail = client.get("/api/v1/opportunities/syn-opp-01/scores/detail").json()
    assert detail["formula_version"] == "score-v1"
    # El fixture no tiene resiliencia temporal: el índice internacional y el integrado quedan NULL.
    assert detail["scores"]["international"]["value"] is None
    assert detail["scores"]["integrated"]["value"] is None
    assert "resiliencia_temporal" in (detail["scores"]["international"]["reason"] or "")
    assert detail["scores"]["integrated"]["state"] == "NOT_AVAILABLE"


def test_cohort_ranking_is_blocked_then_orders_nulls_last(
    client: TestClient, seeded_db: Session, mode: Any
) -> None:
    body = {"opportunity_ids": ["syn-opp-01", "syn-opp-02", "syn-opp-03"]}
    mode("approved_scope", True)
    assert client.post("/api/v1/cohorts/ranking", json=body).status_code == 403

    seeded_db.add(_approval())
    seeded_db.commit()
    ranking = client.post("/api/v1/cohorts/ranking", json=body).json()["ranking"]
    assert [r["opportunity_id"] for r in ranking] == ["syn-opp-01", "syn-opp-02", "syn-opp-03"]
    assert all(r["integrated"] is None for r in ranking)


def test_compare_keeps_scores_restricted_without_approval(client: TestClient) -> None:
    body = client.post(
        "/api/v1/compare", json={"opportunity_ids": ["syn-opp-01", "syn-opp-02"]}
    ).json()
    value = body["items"][0]["values"]["scores.integrated"]
    assert value["state"] == "RESTRICTED"
    assert value["value"] is None


def test_policy_capabilities_show_the_approval_reference(
    client: TestClient, seeded_db: Session, mode: Any
) -> None:
    seeded_db.add(_approval())
    seeded_db.commit()
    mode("approved_scope", True)
    caps = {c["id"]: c for c in client.get("/api/v1/policy/capabilities").json()}
    assert caps["advanced_scores"]["allowed"] is True
    assert "DOC-REVISION-DERIVADAS-001" in caps["advanced_scores"]["reason"]
    assert caps["derived_metrics"]["allowed"] is False
