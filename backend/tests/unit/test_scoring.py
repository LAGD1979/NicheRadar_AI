"""Índices orientativos (M4): reglas puras. Sin base de datos ni red."""

import pytest

from app.domain import scoring


def _full(weights: dict[str, float], value: float = 1.0) -> dict[str, float | None]:
    return {name: value for name in weights}


def test_subindex_is_weighted_mean_when_every_dimension_exists() -> None:
    result = scoring.subindex(scoring.SPANISH_WEIGHTS, _full(scoring.SPANISH_WEIGHTS, 0.5))
    assert result.value == 50.0
    assert result.missing == []


def test_one_missing_dimension_makes_the_subindex_null_not_zero() -> None:
    ratios = _full(scoring.SPANISH_WEIGHTS, 1.0)
    ratios["exito_accesible"] = None
    result = scoring.subindex(scoring.SPANISH_WEIGHTS, ratios)
    assert result.value is None
    assert result.missing == ["exito_accesible"]


def test_integrated_is_null_when_any_subindex_is_null() -> None:
    result = scoring.integrated({"international": 80.0, "spanish": None, "operational": 60.0})
    assert result.value is None
    assert result.missing == ["spanish"]


def test_integrated_uses_the_35_40_25_weights() -> None:
    result = scoring.integrated({"international": 100.0, "spanish": 50.0, "operational": 0.0})
    assert result.value == round((35 * 100 + 40 * 50 + 25 * 0) / 100, 2)


def test_weights_sum_to_their_documented_totals() -> None:
    assert sum(scoring.INTERNATIONAL_WEIGHTS.values()) == 100
    assert sum(scoring.SPANISH_WEIGHTS.values()) == 100
    assert sum(scoring.OPERATIONAL_WEIGHTS.values()) == 100
    assert sum(scoring.INTEGRATED_WEIGHTS.values()) == 100


@pytest.mark.parametrize(
    ("state", "ratio"),
    [
        ("REPLICATED", 1.0),
        ("PROMISING", 0.6),
        ("SINGLE_OUTLIER", 0.2),
        ("UNKNOWN", None),
        (None, None),
    ],
)
def test_replication_mapping(state: str | None, ratio: float | None) -> None:
    assert scoring.replication_ratio(state) == ratio


def test_unknown_saturation_and_unproven_demand_do_not_score() -> None:
    # T10 / §3.6: desconocido o no demostrado no es cero ni es puntuación alta.
    assert scoring.saturation_ratio("UNKNOWN") is None
    assert scoring.demand_ratio("UNPROVEN") is None
    assert scoring.demand_ratio("NOT_OBSERVED") is None


def test_simpler_production_scores_higher() -> None:
    assert scoring.complexity_ratio(1) == 1.0
    assert scoring.complexity_ratio(5) == 0.0
    assert scoring.complexity_ratio(None) is None
    assert scoring.complexity_ratio(9) is None


def test_cost_is_normalised_inside_the_cohort() -> None:
    assert scoring.cost_ratio(2.0, 2.0, 6.0) == 1.0  # el más barato puntúa 1
    assert scoring.cost_ratio(6.0, 2.0, 6.0) == 0.0
    assert scoring.cost_ratio(4.0, 2.0, 6.0) == 0.5
    assert scoring.cost_ratio(4.0, None, None) is None  # sin cohorte no hay índice
    assert scoring.cost_ratio(None, 2.0, 6.0) is None


def test_channels_reach_full_score_at_three_independent_creators() -> None:
    assert scoring.channels_ratio(3) == 1.0
    assert scoring.channels_ratio(1) == pytest.approx(1 / 3)
    assert scoring.channels_ratio(None) is None


def test_ranking_is_stable_and_puts_nulls_last() -> None:
    items = [("opp-b", 70.0), ("opp-a", None), ("opp-c", 70.0), ("opp-d", 90.0)]
    assert [i for i, _ in scoring.rank(items)] == ["opp-d", "opp-b", "opp-c", "opp-a"]
    assert [i for i, _ in scoring.rank(list(reversed(items)))] == [
        "opp-d",
        "opp-b",
        "opp-c",
        "opp-a",
    ]
