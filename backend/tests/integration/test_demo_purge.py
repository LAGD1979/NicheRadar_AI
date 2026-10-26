"""Quitar la demo sin tocar lo real, y no cargarla con DEMO_MODE=false (D-65)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models as m
from app.demo import purge, seed
from app.demo.seed import load_fixture
from tests.conftest import truncate_all

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


def _count(session: Session, model: type[m.Base]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _add_real_data(session: Session) -> dict[str, str]:
    """Una oportunidad real, más un video real anotado a una oportunidad de la demo."""
    niche = m.Niche(
        id="real-niche",
        canonical_name_es="Nicho real",
        definition="Definición real suficiente.",
        exclusions_json=[],
        taxonomy_version="user-v1",
        source_data_type="HUMAN",
    )
    fmt = m.Format(
        id="real-format",
        canonical_name_es="Formato real",
        story_structure="Estructura real.",
        visual_grammar="",
        audio_grammar="",
        requirements_json={},
        taxonomy_version="user-v1",
        source_data_type="HUMAN",
    )
    session.add_all([niche, fmt])
    session.flush()
    opportunity = m.Opportunity(
        id="real-opp",
        niche_id=niche.id,
        format_id=fmt.id,
        target_lang="es",
        video_type="LONG",
        source_languages_json=[],
        status="SCREENED",
    )
    # Canal de la demo que ahora también tiene un video real: no debe borrarse.
    real_video = m.Video(
        id="real-video",
        youtube_video_id="REALVID0001",
        channel_id="syn-ch-01",
        title="Video real de un canal sintético",
        published_at=NOW,
        duration_seconds=900,
        video_type="LONG",
        video_type_evidence="x",
        language_state="es",
        language_confidence="HIGH",
        view_count=5000,
        provider="youtube_official",
        observed_at=NOW,
        source_data_type="OFFICIAL",
    )
    other_channel = m.Channel(
        id="real-channel",
        youtube_channel_id="UCreal0000000001",
        title_current="Canal real",
        subscriber_count=900,
        subscriber_band="X",
        language_state="UNKNOWN",
        provider="youtube_official",
        observed_at=NOW,
        source_data_type="OFFICIAL",
        owner_authorized=False,
    )
    session.add_all([opportunity, real_video, other_channel])
    session.flush()
    session.add(
        m.VideoAnnotation(
            id="ann-real",
            video_id=real_video.id,
            opportunity_id="syn-opp-01",
            same_format_confidence="MEDIUM",
            label_source="HUMAN",
            rationale="Anotación real.",
            reviewed_by="local_owner",
        )
    )
    session.commit()
    return {"opportunity": opportunity.id, "video": real_video.id}


def test_dry_run_reports_and_deletes_nothing(seeded_db: Session, capsys: Any) -> None:
    _add_real_data(seeded_db)
    before = {model: _count(seeded_db, model) for model in (m.Opportunity, m.Video, m.Niche)}
    summary = purge.plan(seeded_db, load_fixture())
    assert summary["borrar"]["opportunities"] == 8
    assert summary["borrar"]["videos"] == 20
    assert summary["borrar"]["video_annotations"] >= 1  # incluye la anotación real a la demo
    assert summary["conservar"]["oportunidades_reales"] == 1
    assert summary["conservar"]["videos_reales"] == 1
    after = {model: _count(seeded_db, model) for model in (m.Opportunity, m.Video, m.Niche)}
    assert before == after


def test_apply_removes_the_demo_and_keeps_everything_real(seeded_db: Session) -> None:
    ids = _add_real_data(seeded_db)
    data = load_fixture()
    purge.apply(seeded_db, data)
    seeded_db.commit()
    assert _count(seeded_db, m.Opportunity) == 1
    assert seeded_db.get(m.Opportunity, ids["opportunity"]) is not None
    assert seeded_db.get(m.Video, ids["video"]) is not None  # el video real sigue
    assert seeded_db.get(m.Channel, "syn-ch-01") is not None  # su canal sintético se queda
    assert seeded_db.get(m.Channel, "real-channel") is not None
    assert _count(seeded_db, m.Video) == 1
    assert _count(seeded_db, m.Niche) == 1
    assert _count(seeded_db, m.Evaluation) == 0
    assert _count(seeded_db, m.OpportunityEvidence) == 0
    assert _count(seeded_db, m.VideoAnnotation) == 0
    assert seeded_db.get(m.ResearchRun, data["run"]["id"]) is None


def test_other_synthetic_channels_without_real_videos_are_removed(seeded_db: Session) -> None:
    _add_real_data(seeded_db)
    purge.apply(seeded_db, load_fixture())
    seeded_db.commit()
    remaining = set(seeded_db.scalars(select(m.Channel.id)))
    assert remaining == {"syn-ch-01", "real-channel"}


def test_purge_is_idempotent(seeded_db: Session) -> None:
    data = load_fixture()
    purge.apply(seeded_db, data)
    again = purge.apply(seeded_db, data)
    assert sum(again.values()) == 0


def test_a_real_opportunity_on_a_demo_niche_blocks_the_purge(seeded_db: Session) -> None:
    seeded_db.add(
        m.Opportunity(
            id="real-on-demo-niche",
            niche_id="syn-niche-01",
            format_id="syn-fmt-04",
            target_lang="es",
            video_type="SHORT",
            source_languages_json=[],
            status="SCREENED",
        )
    )
    seeded_db.commit()
    assert purge.blockers(seeded_db, purge.fixture_ids(load_fixture())) == ["real-on-demo-niche"]


def test_cli_defaults_to_simulation(seeded_db: Session, capsys: Any) -> None:
    assert purge.main([]) == 0
    assert "Simulación" in capsys.readouterr().out
    assert _count(seeded_db, m.Opportunity) == 8  # no se borró nada
    assert purge.main(["--apply"]) == 0
    seeded_db.expire_all()
    assert _count(seeded_db, m.Opportunity) == 0


def test_cli_stops_when_a_real_opportunity_depends_on_the_demo(
    seeded_db: Session, capsys: Any
) -> None:
    seeded_db.add(
        m.Opportunity(
            id="real-on-demo-niche",
            niche_id="syn-niche-01",
            format_id="syn-fmt-04",
            target_lang="es",
            video_type="SHORT",
            source_languages_json=[],
            status="SCREENED",
        )
    )
    seeded_db.commit()
    assert purge.main(["--apply"]) == 2
    assert "DETENIDO" in capsys.readouterr().out
    assert _count(seeded_db, m.Opportunity) == 9


# --- DEMO_MODE=false ------------------------------------------------------------------------


def test_seed_is_skipped_when_demo_mode_is_off(
    empty_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    truncate_all(empty_db)
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    seed.main()
    assert _count(empty_db, m.Niche) == 0
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    seed.main()
    empty_db.expire_all()
    assert _count(empty_db, m.Niche) == 5


def test_demo_run_is_refused_and_the_banner_disappears_without_demo(
    client: TestClient, seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    purge.apply(seeded_db, load_fixture())
    seeded_db.commit()
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    refused = client.post("/api/v1/research-runs", json={"kind": "demo"})
    assert refused.status_code == 409
    assert refused.json()["code"] == "DEMO_DISABLED"
    config = client.get("/api/v1/config/public").json()
    assert config["demo_mode"] is False
    assert config["synthetic_banner"] is False
    assert config["data_mode"] == "SYNTHETIC"  # sin videos reales aún, pero el banner ya no aparece
    providers = {p["id"]: p for p in client.get("/api/v1/providers").json()}
    assert providers["synthetic_fixture"]["status"] == "DISABLED"
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
