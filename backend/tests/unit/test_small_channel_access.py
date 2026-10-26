"""Éxito accesible a canales pequeños: nunca cero por falta de dato (spec §10.4, T10)."""

from app.domain.small_channel_access import ExactCompetitor, assess


def _c(n: int, *, views: int | None = 120_000, subs: int | None = 8_000) -> ExactCompetitor:
    return ExactCompetitor(
        video_id=f"V{n}", channel_id=f"C{n}", view_count=views, subscriber_count=subs
    )


def test_no_exact_competitors_is_not_scored() -> None:
    result = assess([])
    assert result["state"] == "NO_EXACT_MATCHES"
    assert result["ratio"] is None


def test_small_sample_is_not_scored() -> None:
    result = assess([_c(1), _c(2)])
    assert result["state"] == "INSUFFICIENT_SAMPLE"
    assert result["ratio"] is None
    assert result["evaluated"] == 2


def test_all_small_channels_with_high_views_scores_one() -> None:
    result = assess([_c(i) for i in range(4)])
    assert result["state"] == "OBSERVED"
    assert result["ratio"] == 1.0
    assert result["small_channel_successes"] == 4


def test_large_channels_and_low_views_do_not_count_as_success() -> None:
    items = [_c(1), _c(2, subs=3_000_000), _c(3, views=900), _c(4, views=70_000, subs=20_000)]
    result = assess(items)
    assert result["evaluated"] == 4
    assert result["small_channel_successes"] == 2
    assert result["ratio"] == 0.5


def test_missing_values_are_excluded_not_zero() -> None:
    items = [_c(1), _c(2), _c(3, views=None), _c(4, subs=None)]
    result = assess(items)
    assert result["exact_competitors"] == 4
    assert result["evaluated"] == 2
    assert result["state"] == "INSUFFICIENT_SAMPLE"  # 2 < 3: no se puntúa con lo que falta


def test_zero_subscribers_is_a_real_small_channel() -> None:
    items = [_c(1, subs=0), _c(2, subs=0), _c(3, subs=0)]
    result = assess(items)
    assert result["small_channels"] == 3
    assert result["ratio"] == 1.0


def test_same_video_from_two_queries_counts_once() -> None:
    result = assess([_c(1), _c(1), _c(2), _c(3)])
    assert result["exact_competitors"] == 3
