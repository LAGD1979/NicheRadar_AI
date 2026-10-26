"""Replicación internacional contra PostgreSQL: compuerta, evidencia, versiones y caducidad."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models as m
from app.providers.vidiq_mcp import OutlierParams, OutlierVideo
from app.services import retention_service, vidiq_service
from app.services.vidiq_service import OutlierSearch

NOW = datetime.now(UTC)


class _Source:
    def __init__(self, items: list[OutlierVideo]) -> None:
        self.items = items

    def outliers(self, params: OutlierParams) -> tuple[list[OutlierVideo], int]:
        return self.items, 0


def _item(n: int, channel: str, weeks: int) -> OutlierVideo:
    published = (NOW - timedelta(days=60) + timedelta(weeks=weeks)).isoformat()
    base: dict[str, Any] = {
        "youtube_video_id": f"REPVID{n:04d}",
        "title": f"[SINTÉTICO] video {n}",
        "published_at": published,
        "duration_seconds": 900,
        "youtube_channel_id": channel,
        "channel_title": f"Canal {channel}",
        "channel_country": "US",
        "subscriber_count": 8000,
        "view_count": 120000,
        "breakout_score": 10.0,
        "views_per_hour": 5.0,
        "engagement_rate": 0.01,
        "video_type": "long",
        "trend_categories": (),
        "ai_labeled": None,
    }
    return OutlierVideo(**base)


def _load(session: Session, count: int = 6) -> None:
    items = [_item(i, f"UCrep{i:08d}", weeks=i) for i in range(count)]
    vidiq_service.run_outlier_discovery(
        session,
        _Source(items),
        get_settings(),
        run_id="run-rep",
        searches=[OutlierSearch(OutlierParams())],
        completed_keys=set(),
        max_calls=1,
        now=NOW,
    )
    session.commit()


def _taxonomy(client: TestClient) -> tuple[str, str]:
    niche = client.post(
        "/api/v1/taxonomy/niches",
        json={"name": "Nicho de replicación", "definition": "Definición suficientemente larga."},
    ).json()["id"]
    fmt = client.post(
        "/api/v1/taxonomy/formats",
        json={
            "name": "Formato de replicación",
            "story_structure": "Estructura suficientemente larga.",
        },
    ).json()["id"]
    return niche, fmt


def _annotate(
    client: TestClient, db_id: str, niche: str, fmt: str, confidence: str = "HIGH"
) -> Any:
    return client.post(
        f"/api/v1/videos/{db_id}/annotations",
        json={
            "niche_id": niche,
            "format_id": fmt,
            "same_format_confidence": confidence,
            "rationale": "Mismo formato según la categoría del proveedor.",
        },
    )


def _video_ids(client: TestClient) -> list[str]:
    items = client.get("/api/v1/videos", params={"provider": "vidiq_api", "page_size": 50}).json()
    return [v["id"] for v in items["items"] if v["title"].startswith("[SINTÉTICO] video")]


def _approval() -> m.PolicyApproval:
    return m.PolicyApproval(
        id="appr-derived",
        provider="vidiq_api",
        capability="derived_metrics",
        scope="pruebas",
        status="ACTIVE",
        approval_ref="DOC-PRUEBA-DERIVADAS",
        reviewed_by="local_owner",
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
        notes="Aprobación de prueba.",
    )


@pytest.fixture
def open_gate(monkeypatch: pytest.MonkeyPatch, seeded_db: Session) -> Iterator[None]:
    seeded_db.add(_approval())
    seeded_db.commit()
    monkeypatch.setenv("COMPLIANCE_MODE", "approved_scope")
    monkeypatch.setenv("ADVANCED_ANALYTICS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("COMPLIANCE_MODE", "restricted")
    monkeypatch.setenv("ADVANCED_ANALYTICS_ENABLED", "false")
    get_settings.cache_clear()


def test_restricted_gate_computes_nothing(client: TestClient, seeded_db: Session) -> None:
    _load(seeded_db, 6)
    niche, fmt = _taxonomy(client)
    response = _annotate(client, _video_ids(client)[0], niche, fmt)
    assert response.status_code == 201
    assert response.json()["replication_state"] == "RESTRICTED"
    opp_id = response.json()["opportunity_id"]
    assert client.post(f"/api/v1/opportunities/{opp_id}/replication/refresh").status_code == 403
    assert (
        seeded_db.scalar(
            select(func.count())
            .select_from(m.Evaluation)
            .where(m.Evaluation.opportunity_id == opp_id)
        )
        == 0
    )


def test_six_channels_over_six_weeks_become_replicated(
    client: TestClient, seeded_db: Session, open_gate: None
) -> None:
    _load(seeded_db, 6)
    niche, fmt = _taxonomy(client)
    states = [_annotate(client, vid, niche, fmt).json() for vid in _video_ids(client)]
    assert states[0]["replication_state"] == "SINGLE_OUTLIER"  # un solo canal
    assert states[-1]["replication_state"] == "REPLICATED"
    opp_id = states[-1]["opportunity_id"]

    detail = client.get(f"/api/v1/opportunities/{opp_id}").json()
    intl = detail["evaluation"]["international"]
    assert intl["replication_state"] == "REPLICATED"
    assert intl["independent_channels_observed"] == 6
    assert intl["independence_verified"] is False
    assert intl["sample_bias_warning"] == "coverage_nonrepresentative"
    assert len(detail["evidence"]) == 6
    assert {e["market"] for e in detail["evidence"]} == {"SOURCE_MARKET"}
    assert detail["evaluation"]["recommendation"] != "WATCHLIST"


def test_refresh_is_idempotent_and_creates_no_duplicate_versions(
    client: TestClient, seeded_db: Session, open_gate: None
) -> None:
    _load(seeded_db, 6)
    niche, fmt = _taxonomy(client)
    last: dict[str, Any] = {}
    for vid in _video_ids(client):
        last = _annotate(client, vid, niche, fmt).json()
    opp_id = last["opportunity_id"]
    before = client.get(f"/api/v1/opportunities/{opp_id}").json()["evaluation"][
        "evaluation_version"
    ]
    for _ in range(3):
        assert client.post(f"/api/v1/opportunities/{opp_id}/replication/refresh").status_code == 200
    after = client.get(f"/api/v1/opportunities/{opp_id}").json()["evaluation"]["evaluation_version"]
    assert after == before
    assert (
        seeded_db.scalar(
            select(func.count())
            .select_from(m.OpportunityEvidence)
            .where(m.OpportunityEvidence.opportunity_id == opp_id)
        )
        == 6
    )


def test_expired_videos_stop_counting(
    client: TestClient, seeded_db: Session, open_gate: None
) -> None:
    _load(seeded_db, 6)
    niche, fmt = _taxonomy(client)
    last: dict[str, Any] = {}
    for vid in _video_ids(client):
        last = _annotate(client, vid, niche, fmt).json()
    opp_id = last["opportunity_id"]
    retention_service.purge_expired(seeded_db, NOW + timedelta(days=40))
    seeded_db.commit()
    result = client.post(f"/api/v1/opportunities/{opp_id}/replication/refresh").json()
    assert result["state"] == "UNKNOWN"
    assert result["result"]["relevant_videos_observed"] == 0


def test_low_confidence_annotations_do_not_replicate(
    client: TestClient, seeded_db: Session, open_gate: None
) -> None:
    _load(seeded_db, 6)
    niche, fmt = _taxonomy(client)
    last: dict[str, Any] = {}
    for vid in _video_ids(client):
        last = _annotate(client, vid, niche, fmt, confidence="LOW").json()
    assert last["replication_state"] == "UNKNOWN"
