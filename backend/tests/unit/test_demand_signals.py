"""Señales de demanda: nunca se declara ausencia por falta de datos (spec §3.6)."""

from app.domain.demand_signals import (
    CONSUMPTION,
    KEYWORDS,
    TRENDS,
    SignalRules,
    TrendSample,
    combine,
    consumption_signal,
    keyword_signal,
    trends_signal,
)


def _weeks(values: list[int | None], partial_last: bool = False) -> list[TrendSample]:
    samples = [TrendSample(v, False) for v in values]
    if partial_last and samples:
        samples[-1] = TrendSample(samples[-1].value, True)
    return samples


def test_sustained_interest_is_a_present_signal() -> None:
    result = trends_signal(_weeks([40] * 52))
    assert result["state"] == "PRESENT"
    assert result["relative_index"] is True
    assert result["recent_mean"] == 40


def test_low_interest_is_observed_as_not_present() -> None:
    result = trends_signal(_weeks([3] * 52))
    assert result["state"] == "NOT_PRESENT"
    assert result["reason"] == "LOW_RELATIVE_INTEREST"


def test_collapsing_interest_is_not_present() -> None:
    result = trends_signal(_weeks([80] * 39 + [20] * 13))
    assert result["state"] == "NOT_PRESENT"
    assert result["reason"] == "INTEREST_DECLINING"


def test_missing_weeks_are_unknown_not_zero() -> None:
    result = trends_signal(_weeks([None] * 52))
    assert result["state"] == "UNKNOWN"
    few = trends_signal(_weeks([50] * 10))
    assert few["state"] == "UNKNOWN"
    assert few["reason"] == "INSUFFICIENT_DATA"


def test_recent_gaps_do_not_pass_as_data() -> None:
    values: list[int | None] = [50] * 40 + [None] * 12
    result = trends_signal(_weeks(values))
    assert result["state"] == "UNKNOWN"
    assert result["reason"] == "INSUFFICIENT_RECENT_DATA"


def test_partial_current_week_is_ignored() -> None:
    result = trends_signal(_weeks([40] * 51 + [0], partial_last=True))
    assert result["state"] == "PRESENT"
    assert result["weeks_total"] == 51


def test_keyword_volume_rules() -> None:
    assert keyword_signal(22_318, 55.9)["state"] == "PRESENT"
    assert keyword_signal(400, 10.0)["reason"] == "BELOW_MIN_VOLUME"
    assert keyword_signal(5_000, -80.0)["reason"] == "SEARCHES_FALLING"
    unknown = keyword_signal(None, None)
    assert unknown["state"] == "UNKNOWN"
    assert keyword_signal(5_000, None)["state"] == "PRESENT"  # el crecimiento puede ser desconocido


def test_consumption_needs_enough_reviewed_exact_competitors() -> None:
    assert consumption_signal({})["reason"] == "NO_EXACT_MATCHES"
    assert consumption_signal({"a": 90_000, "b": 80_000})["reason"] == "INSUFFICIENT_SAMPLE"
    present = consumption_signal({"a": 90_000, "b": 80_000, "c": 60_000})
    assert present["state"] == "PRESENT"
    weak = consumption_signal({"a": 900, "b": 800, "c": 600})
    assert weak["state"] == "NOT_PRESENT"
    missing = consumption_signal({"a": None, "b": None, "c": 70_000})
    assert missing["state"] == "UNKNOWN"


def test_two_families_make_two_independent_signals() -> None:
    result = combine(
        [
            {"family": TRENDS, "state": "PRESENT"},
            {"family": KEYWORDS, "state": "PRESENT"},
            {"family": CONSUMPTION, "state": "UNKNOWN"},
        ]
    )
    assert result["independent_signals"] == 2
    assert result["present_families"] == [TRENDS, KEYWORDS]


def test_several_keywords_from_one_source_count_once() -> None:
    result = combine([{"family": KEYWORDS, "state": "PRESENT"} for _ in range(5)])
    assert result["independent_signals"] == 1


def test_one_present_keyword_wins_over_weaker_ones_in_its_family() -> None:
    result = combine(
        [
            {"family": KEYWORDS, "state": "NOT_PRESENT"},
            {"family": KEYWORDS, "state": "PRESENT"},
            {"family": KEYWORDS, "state": "UNKNOWN"},
        ]
    )
    assert result["family_states"][KEYWORDS] == "PRESENT"


def test_no_signals_gives_zero_not_a_negative_conclusion() -> None:
    result = combine([])
    assert result["independent_signals"] == 0
    assert set(result["family_states"].values()) == {"UNKNOWN"}


def test_rules_are_configurable() -> None:
    strict = SignalRules(keywords_min_monthly_searches=50_000)
    assert keyword_signal(22_318, 10, strict)["state"] == "NOT_PRESENT"
