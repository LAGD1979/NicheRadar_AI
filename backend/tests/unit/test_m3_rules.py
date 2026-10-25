"""Costos, compuertas de decisión y neutralización de exportación (M3). Sin base de datos."""

import pytest

from app.domain import costs
from app.domain.decision import DecisionInput, decide
from app.services.feasibility_service import neutralize, to_csv


def _line(name: str, quantity: float, **prices: float | None) -> costs.CostLine:
    return costs.CostLine(name=name, unit="unidad", quantity=quantity, prices=dict(prices))


# --- costos (T15) ----------------------------------------------------------------------------


def test_total_is_the_sum_when_every_price_is_known() -> None:
    lines = [
        _line("TTS", 2, low=1.0, base=1.5, high=2.0),
        _line("imágenes", 10, low=0.1, base=0.2, high=0.3),
    ]
    result = costs.compute(lines)
    # TTS: 2 x precio; imágenes: 10 x precio. Bajo 2+1, base 3+2, alto 4+3.
    assert result.totals == {"low": 3.0, "base": 5.0, "high": 7.0}
    assert result.missing == {"low": [], "base": [], "high": []}


def test_missing_tts_price_makes_total_null_not_zero() -> None:
    # T15: el precio del TTS no existe → el total es NULL, nunca 0.
    lines = [
        _line("TTS", 2, low=None, base=None, high=None),
        _line("imágenes", 10, low=0.1, base=0.2, high=0.3),
    ]
    result = costs.compute(lines)
    assert result.totals == {"low": None, "base": None, "high": None}
    assert result.missing["base"] == ["TTS"]


def test_only_the_scenario_with_a_gap_is_null() -> None:
    lines = [_line("TTS", 1, low=1.0, base=None, high=2.0)]
    result = costs.compute(lines)
    assert result.totals == {"low": 1.0, "base": None, "high": 2.0}


def test_zero_quantity_still_needs_a_price() -> None:
    # Cantidad 0 no es precio 0: una línea sin precio sigue siendo un dato faltante.
    result = costs.compute([_line("música", 0, low=None, base=None, high=None)])
    assert result.totals["base"] is None


def test_planned_words_are_information_not_cost() -> None:
    assert costs.planned_words(10, 150) == 1500


# --- compuertas de decisión ------------------------------------------------------------------


def _input(**overrides: object) -> DecisionInput:
    base: dict[str, object] = {
        "replication": "REPLICATED",
        "spanish_decision": "POTENTIAL_GAP",
        "demand": "OBSERVED",
        "queries_run": 8,
        "confidence": "MEDIUM",
        "faceless": "FACELESS_LIKELY",
        "complexity": 2,
        "rights": "LOW",
    }
    base.update(overrides)
    return DecisionInput(**base)  # type: ignore[arg-type]


def test_ready_for_pilot_needs_every_condition() -> None:
    decision = decide(_input())
    assert decision.recommendation == "READY_FOR_PILOT"
    assert decision.gates == []


def test_no_demand_never_reaches_ready_and_points_to_demand_pilot() -> None:
    # T11 / §3.6: sin demanda demostrada, piloto de validación de demanda, no lanzamiento.
    decision = decide(_input(demand="UNPROVEN", spanish_decision="DEMAND_UNPROVEN"))
    assert decision.recommendation == "VALIDATE_DEMAND_PILOT"
    assert "DEMAND_UNPROVEN" in decision.gates


def test_high_copyright_risk_rejects_even_with_strong_evidence() -> None:
    decision = decide(_input(rights="HIGH"))
    assert decision.recommendation == "REJECT"
    assert "HIGH_COPYRIGHT_RISK" in decision.gates


def test_crowded_spanish_market_goes_to_watchlist() -> None:
    assert (
        decide(_input(spanish_decision="CROWDED", demand="OBSERVED")).recommendation == "WATCHLIST"
    )


def test_unknown_rights_and_faceless_are_gates_not_assumptions() -> None:
    decision = decide(_input(rights="UNKNOWN", faceless="UNKNOWN"))
    assert decision.recommendation != "READY_FOR_PILOT"
    assert "RIGHTS_NOT_ASSESSED" in decision.gates
    assert "FACELESS_NOT_ASSESSED" in decision.gates


def test_missing_complexity_blocks_ready() -> None:
    decision = decide(_input(complexity=None))
    assert decision.recommendation == "MORE_RESEARCH"
    assert "COMPLEXITY_NOT_ASSESSED" in decision.gates


def test_too_few_queries_is_insufficient_evidence() -> None:
    decision = decide(_input(queries_run=3))
    assert decision.recommendation == "MORE_RESEARCH"
    assert "INSUFFICIENT_EVIDENCE" in decision.gates


def test_complex_production_blocks_ready() -> None:
    assert decide(_input(complexity=4)).recommendation == "MORE_RESEARCH"


@pytest.mark.parametrize("replication", [None, "SINGLE_OUTLIER"])
def test_weak_international_evidence_never_recommends_pilot(replication: str | None) -> None:
    assert decide(_input(replication=replication)).recommendation == "MORE_RESEARCH"


# --- exportación (T20) -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw", ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\tcmd", "\rcmd"]
)
def test_formula_like_text_is_prefixed(raw: str) -> None:
    assert neutralize(raw) == "'" + raw


def test_plain_text_and_numbers_are_untouched() -> None:
    assert neutralize("Historia") == "Historia"
    assert neutralize(3.2) == 3.2
    assert neutralize(None) is None


def test_csv_never_emits_a_raw_formula() -> None:
    row = {
        "id": "x",
        "niche": "=cmd|' /C calc'!A0",
        "format": "f",
        "target_lang": "es",
        "video_type": "LONG",
        "status": "s",
        "recommendation": "MORE_RESEARCH",
        "gates": "g",
        "confidence": "LOW",
        "saturation_es": "",
        "spanish_demand_state": "",
        "entry_decision": "",
        "faceless_state": "",
        "complexity_1_to_5": "",
        "rights_risk": "",
        "usd_base": "",
        "data_source": "d",
        "observed_at": "",
        "warning": "w",
    }
    text = to_csv([row])
    body = text.splitlines()[1]
    assert body.startswith("x,'=cmd")
