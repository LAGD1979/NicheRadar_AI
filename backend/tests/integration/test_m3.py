"""M3 contra PostgreSQL: costos, factibilidad revisada, recomendación y exportación."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m


def _cost_body(tts_price: float | None = 1.5) -> dict[str, Any]:
    return {
        "duration_minutes": 10,
        "words_per_minute": 150,
        "lines": [
            {
                "name": "TTS",
                "unit": "1000 caracteres",
                "quantity": 9,
                "prices": {"low": 1.0, "base": tts_price, "high": 2.0},
            },
            {
                "name": "imágenes",
                "unit": "imagen",
                "quantity": 20,
                "prices": {"low": 0.01, "base": 0.02, "high": 0.03},
            },
        ],
    }


def _feasibility(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "faceless_state": "FACELESS_LIKELY",
        "complexity_1_to_5": 2,
        "rights_risk": "LOW",
        "rights_notes": None,
        "faceless_reason": "Narración con ilustraciones originales; sin rostros ni metraje ajeno.",
        "human_review_required": True,
        "human_minutes_per_video": 180,
        "ai_pipeline_coverage_pct": 40,
    }
    body.update(overrides)
    return body


def test_cost_model_with_missing_price_has_null_total(client: TestClient) -> None:
    # T15: sin precio de TTS en el escenario base, ese total queda NULL, no 0.
    response = client.post(
        "/api/v1/opportunities/syn-opp-01/cost-model", json=_cost_body(tts_price=None)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["scenarios"]["usd_per_video"]["base"] is None
    assert body["missing"]["base"] == ["TTS"]
    assert body["scenarios"]["usd_per_video"]["low"] is not None


def test_cost_model_is_versioned_and_feeds_the_evaluation(client: TestClient) -> None:
    client.post("/api/v1/opportunities/syn-opp-01/cost-model", json=_cost_body(tts_price=1.0))
    client.post("/api/v1/opportunities/syn-opp-01/cost-model", json=_cost_body(tts_price=1.5))
    latest = client.get("/api/v1/opportunities/syn-opp-01/cost-model").json()
    assert latest["version"] == 2
    detail = client.get("/api/v1/opportunities/syn-opp-01").json()
    assert detail["evaluation"]["feasibility"]["usd_per_video_scenarios"]["base"] is not None
    assert detail["evaluation"]["feasibility"]["costs_are_estimates"] is True


def test_cost_model_rejects_impossible_inputs(client: TestClient) -> None:
    bad = _cost_body()
    bad["words_per_minute"] = 900
    assert client.post("/api/v1/opportunities/syn-opp-01/cost-model", json=bad).status_code == 422


def test_medium_rights_risk_requires_a_reason(client: TestClient) -> None:
    response = client.post(
        "/api/v1/opportunities/syn-opp-01/feasibility",
        json=_feasibility(rights_risk="MEDIUM", rights_notes="corto"),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "RIGHTS_REASON_REQUIRED"


def test_feasibility_appends_a_new_evaluation_with_recommendation(
    client: TestClient, seeded_db: Session
) -> None:
    before = seeded_db.scalars(
        select(m.Evaluation).where(m.Evaluation.opportunity_id == "syn-opp-01")
    ).all()
    response = client.post("/api/v1/opportunities/syn-opp-01/feasibility", json=_feasibility())
    assert response.status_code == 201
    body = response.json()
    assert body["evaluation_version"] == max(e.evaluation_version for e in before) + 1
    assert body["recommendation"] in {
        "READY_FOR_PILOT",
        "VALIDATE_DEMAND_PILOT",
        "MORE_RESEARCH",
        "WATCHLIST",
        "REJECT",
    }
    # El fixture sintético dice demanda INDICATIVA y confianza MEDIA: el piloto es alcanzable.
    assert body["recommendation"] == "READY_FOR_PILOT"
    assert body["gates"] == []


def test_unproven_demand_blocks_ready_even_with_good_production(client: TestClient) -> None:
    # syn-opp-03: demanda española no demostrada en el fixture.
    body = client.post("/api/v1/opportunities/syn-opp-03/feasibility", json=_feasibility()).json()
    assert body["recommendation"] == "VALIDATE_DEMAND_PILOT"
    assert "DEMAND_UNPROVEN" in body["gates"]


def test_high_rights_risk_rejects_the_opportunity(client: TestClient) -> None:
    response = client.post(
        "/api/v1/opportunities/syn-opp-05/feasibility",
        json=_feasibility(
            rights_risk="HIGH",
            rights_notes="Depende de metraje de archivo de terceros sin licencia.",
            faceless_state="NOT_FACELESS",
        ),
    )
    assert response.json()["recommendation"] == "REJECT"
    assert "HIGH_COPYRIGHT_RISK" in response.json()["gates"]


def test_compare_shows_recommendation_and_gates(client: TestClient) -> None:
    ids = ["syn-opp-01", "syn-opp-02", "syn-opp-03", "syn-opp-04"]
    body = client.post("/api/v1/compare", json={"opportunity_ids": ids}).json()
    keys = {f["key"] for f in body["fields"]}
    assert {"recommendation", "gates", "feasibility.human_minutes_per_video"} <= keys
    first = body["items"][0]["values"]
    assert first["recommendation"]["value"]
    assert first["gates"]["state"] in {"AVAILABLE", "NOT_AVAILABLE"}


def test_csv_export_neutralizes_formulas_and_carries_warning(
    client: TestClient, seeded_db: Session
) -> None:
    # T20: una nota con fórmula no se ejecuta en la hoja de cálculo.
    opp = seeded_db.get(m.Opportunity, "syn-opp-02")
    assert opp is not None
    opp.owner_notes = '=HYPERLINK("http://exfiltrar.invalid","clic")'
    seeded_db.commit()
    response = client.get("/api/v1/exports/opportunities.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "=HYPERLINK" not in response.text.replace("'=HYPERLINK", "")
    assert "29 días" in response.text
    header = response.text.splitlines()[0]
    assert "recommendation" in header and "warning" in header


def test_json_export_respects_filters_and_carries_warning(client: TestClient) -> None:
    body = client.get("/api/v1/exports/opportunities.json", params={"saturation_es": "LOW"}).json()
    assert [i["id"] for i in body["items"]] == ["syn-opp-01"]
    assert "29 días" in body["warning"]
    assert body["items"][0]["recommendation"]


def test_cost_model_for_unknown_opportunity_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/opportunities/no-existe/cost-model").status_code == 404
