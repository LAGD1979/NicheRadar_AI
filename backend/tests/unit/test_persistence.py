"""Persistencia de la velocidad: semana 2 contra semana 1 desde la publicación."""

from datetime import UTC, datetime, timedelta

from app.domain.persistence import PersistenceRules, Sample, aggregate, video_persistence

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _series(daily_gains: list[int], offset_days: float = 0.0) -> list[Sample]:
    """Acumulado diario: el primer punto es la publicación (más `offset_days`)."""
    total = 0
    first = START + timedelta(days=offset_days)
    samples = [Sample(first, 0)]
    for day, gain in enumerate(daily_gains, start=1):
        total += gain
        samples.append(Sample(first + timedelta(days=day), total))
    return samples


def _gains(week1: int, week2: int, rest: int = 100, days: int = 30) -> list[int]:
    """Ganancia por día: el día 1 y luego las semanas 1 y 2 definidas, y el resto fijo."""
    out = [week1]  # día 0 a 1 (no entra en ninguna ventana)
    out += [week1] * 7  # días 1 a 8: primera semana
    out += [week2] * 7  # días 8 a 15: segunda semana
    out += [rest] * (days - len(out))
    return out


def test_a_steady_video_keeps_its_speed() -> None:
    result = video_persistence(_series(_gains(1000, 1000)), START)
    assert result["state"] == "OBSERVED"
    assert result["ratio"] == 1.0
    assert result["week1_views_per_day"] == result["week2_views_per_day"] == 1000.0


def test_a_flash_in_the_pan_scores_low() -> None:
    result = video_persistence(_series(_gains(50_000, 500)), START)
    assert result["ratio"] == 0.01


def test_partial_decay_gives_an_intermediate_ratio() -> None:
    assert video_persistence(_series(_gains(10_000, 5_000)), START)["ratio"] == 0.5


def test_acceleration_is_capped_at_one() -> None:
    assert video_persistence(_series(_gains(1_000, 4_000)), START)["ratio"] == 1.0


def test_the_age_of_the_video_does_not_change_the_score() -> None:
    old = _series(_gains(10_000, 5_000, rest=1, days=120))
    young = _series(_gains(10_000, 5_000, rest=1, days=16))
    assert video_persistence(old, START)["ratio"] == video_persistence(young, START)["ratio"] == 0.5


def test_week_four_tail_is_reported_but_not_scored() -> None:
    result = video_persistence(_series(_gains(10_000, 5_000, rest=700, days=40)), START)
    assert result["week4_views_per_day"] == 700.0
    assert result["ratio"] == 0.5
    short = video_persistence(_series(_gains(10_000, 5_000, days=20)), START)
    assert "week4_views_per_day" not in short


def test_history_that_starts_late_is_not_scored() -> None:
    result = video_persistence(_series(_gains(1000, 1000), offset_days=6), START)
    assert result["state"] == "INSUFFICIENT_HISTORY"
    assert result["reason"] == "HISTORY_STARTS_LATE"
    assert result["ratio"] is None


def test_short_history_is_not_scored() -> None:
    result = video_persistence(_series([1000] * 11), START)
    assert result["state"] == "INSUFFICIENT_HISTORY"
    assert result["reason"] == "SHORT_HISTORY"


def test_few_points_are_not_scored_even_with_enough_days() -> None:
    samples = [
        Sample(START, 0),
        Sample(START + timedelta(days=8), 500),
        Sample(START + timedelta(days=20), 900),
    ]
    result = video_persistence(samples, START)
    assert result["reason"] == "FEW_POINTS"


def test_a_video_without_gains_is_not_a_zero_score() -> None:
    result = video_persistence(_series([0] * 30), START)
    assert result["state"] == "NO_VIEW_GAINS"
    assert result["ratio"] is None


def test_missing_views_and_repeated_timestamps_are_ignored() -> None:
    samples = _series(_gains(1000, 1000))
    samples.append(Sample(samples[-1].at, 5))  # marca repetida
    samples.insert(3, Sample(START + timedelta(days=2, hours=1), None))
    result = video_persistence(samples, START)
    assert result["state"] == "OBSERVED"
    assert result["ratio"] == 1.0


def test_data_corrections_count_as_zero_gain_and_are_reported() -> None:
    gains = _gains(1000, 1000)
    gains[10] = -400  # el acumulado baja dentro de las dos primeras semanas
    result = video_persistence(_series(gains), START)
    assert result["data_revisions"] >= 1
    assert result["ratio"] is not None


def test_aggregate_uses_the_median_and_needs_enough_videos() -> None:
    result = aggregate([{"ratio": 0.9}, {"ratio": 0.5}, {"ratio": 0.1}])
    assert result["state"] == "OBSERVED"
    assert result["ratio"] == 0.5
    assert result["definition"] == "views_per_day_week2_over_week1"
    short = aggregate([{"ratio": 0.9}, {"ratio": None}, {"ratio": None}])
    assert short["state"] == "INSUFFICIENT_VIDEOS"
    assert short["ratio"] is None
    assert short["videos_without_enough_history"] == 2
    assert aggregate([])["state"] == "NO_VIDEOS"


def test_aggregate_minimum_is_configurable() -> None:
    assert aggregate([{"ratio": 0.8}], PersistenceRules(min_videos=1))["ratio"] == 0.8
