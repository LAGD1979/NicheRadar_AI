"""Flujo de exploración: filtros de videos, taxonomía propia y anotación a oportunidad."""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.providers.vidiq_mcp import OutlierParams, OutlierVideo
from app.services import vidiq_service
from app.services.vidiq_service import OutlierSearch

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=UTC)


class _Source:
    def __init__(self, items: list[OutlierVideo]) -> None:
        self.items = items

    def outliers(self, params: OutlierParams) -> tuple[list[OutlierVideo], int]:
        return self.items, 0


def _item(video_id: str, breakout: float | None, **over: Any) -> OutlierVideo:
    base: dict[str, Any] = {
        "youtube_video_id": video_id,
        "title": f"[SINTÉTICO] {video_id}",
        "published_at": "2026-09-01T10:00:00+00:00",
        "duration_seconds": 900,
        "youtube_channel_id": f"UC{video_id}",
        "channel_title": "Canal sintético",
        "channel_country": "US",
        "subscriber_count": 5000,
        "view_count": 120000,
        "breakout_score": breakout,
        "views_per_hour": 10.0,
        "engagement_rate": 0.01,
        "video_type": "long",
        "trend_categories": ("video_essay",),
        "ai_labeled": None,
    }
    return OutlierVideo(**{**base, **over})


def _load(session: Session) -> None:
    items = [_item("VIDLOW0001", 2.0), _item("VIDHIGH001", 50.0), _item("VIDNONE001", None)]
    vidiq_service.run_outlier_discovery(
        session,
        _Source(items),
        get_settings(),
        run_id="run-x",
        searches=[OutlierSearch(OutlierParams())],
        completed_keys=set(),
        max_calls=1,
        now=NOW,
    )
    session.commit()


def _titles(client: TestClient, **params: str) -> list[str]:
    body = client.get("/api/v1/videos", params=params).json()
    return [v["youtube_video_id"] for v in body["items"]]


def test_provider_filter_and_breakout_sort(client: TestClient, seeded_db: Session) -> None:
    _load(seeded_db)
    ids = _titles(client, provider="vidiq_api", sort="breakout")
    assert ids == ["VIDHIGH001", "VIDLOW0001", "VIDNONE001"]  # el NULL va al final, no como 0
    assert len(_titles(client, provider="youtube_official")) == 0


def test_video_exposes_vidiq_metrics_and_retention(client: TestClient, seeded_db: Session) -> None:
    _load(seeded_db)
    item = client.get("/api/v1/videos", params={"q": "VIDHIGH001"}).json()["items"][0]
    assert item["provider_metrics"]["vidiq"]["breakout_score"] == 50.0
    assert item["retention_deadline"] is not None
    assert item["opportunities"] == []


def _create_taxonomy(client: TestClient) -> tuple[str, str]:
    niche = client.post(
        "/api/v1/taxonomy/niches",
        json={"name": "Nicho de prueba", "definition": "Definición suficientemente larga."},
    )
    fmt = client.post(
        "/api/v1/taxonomy/formats",
        json={"name": "Formato de prueba", "story_structure": "Tres actos con narración."},
    )
    assert niche.status_code == 201
    assert fmt.status_code == 201
    return niche.json()["id"], fmt.json()["id"]


def test_taxonomy_creation_rejects_duplicates_and_bad_input(client: TestClient) -> None:
    _create_taxonomy(client)
    again = client.post(
        "/api/v1/taxonomy/niches",
        json={"name": "NICHO DE PRUEBA", "definition": "Otra definición suficientemente larga."},
    )
    assert again.status_code == 409
    assert again.json()["code"] == "NICHE_EXISTS"
    short = client.post("/api/v1/taxonomy/niches", json={"name": "ab", "definition": "corta"})
    assert short.status_code == 422
    control = client.post(
        "/api/v1/taxonomy/formats",
        json={"name": "Formato\x07raro", "story_structure": "Estructura suficientemente larga."},
    )
    assert control.status_code == 422
    names = [n["name"] for n in client.get("/api/v1/taxonomy").json()["niches"]]
    assert "Nicho de prueba" in names


def test_annotating_links_video_to_opportunity_and_filters(
    client: TestClient, seeded_db: Session
) -> None:
    _load(seeded_db)
    niche_id, format_id = _create_taxonomy(client)
    videos = client.get("/api/v1/videos", params={"provider": "vidiq_api"}).json()["items"]
    by_ypid = {v["youtube_video_id"]: v["id"] for v in videos}
    body = {
        "niche_id": niche_id,
        "format_id": format_id,
        "same_format_confidence": "MEDIUM",
        "rationale": "Mismo formato de ensayo narrado.",
    }
    first = client.post(f"/api/v1/videos/{by_ypid['VIDHIGH001']}/annotations", json=body)
    second = client.post(f"/api/v1/videos/{by_ypid['VIDLOW0001']}/annotations", json=body)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["opportunity_id"] == second.json()["opportunity_id"]  # una sola oportunidad

    annotated = client.get("/api/v1/videos", params={"provider": "vidiq_api", "annotated": "true"})
    pending = client.get("/api/v1/videos", params={"provider": "vidiq_api", "annotated": "false"})
    assert annotated.json()["total"] == 2
    assert [v["youtube_video_id"] for v in pending.json()["items"]] == ["VIDNONE001"]
    ref = annotated.json()["items"][0]["opportunities"][0]
    assert ref["id"] == first.json()["opportunity_id"]
    assert "Nicho de prueba" in ref["label"]

    detail = client.get(f"/api/v1/opportunities/{ref['id']}")
    assert detail.status_code == 200
