from datetime import UTC, datetime

import pytest

from app.domain.rules import age_hours, subscriber_band

UTC_NOON = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def test_age_for_video_published_now_is_positive_and_bounded() -> None:
    # T03: un video publicado en el mismo instante no da 0 ni división por cero.
    assert age_hours(UTC_NOON, UTC_NOON) == 1.0


def test_age_is_hours_between_timestamps() -> None:
    published = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    assert age_hours(published, UTC_NOON) == pytest.approx(24.0)


def test_future_publication_is_rejected() -> None:
    with pytest.raises(ValueError):
        age_hours(datetime(2026, 10, 21, tzinfo=UTC), UTC_NOON)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError):
        age_hours(datetime(2026, 10, 19, 12), UTC_NOON)


def test_unknown_subscribers_are_not_zero() -> None:
    # T02: NULL es UNKNOWN; cero real es la banda [0,1000).
    assert subscriber_band(None) == "UNKNOWN"
    assert subscriber_band(0) == "[0,1000)"


@pytest.mark.parametrize(
    ("count", "band"),
    [(999, "[0,1000)"), (1000, "[1000,10000)"), (50_000, "[50000,100000)"), (100_000, ">=100000")],
)
def test_subscriber_band_boundaries(count: int, band: str) -> None:
    assert subscriber_band(count) == band
