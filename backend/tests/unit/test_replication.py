"""Reglas de replicación internacional (spec §3.4, §10.3, casos de §14)."""

from datetime import UTC, datetime, timedelta

from app.domain.replication import ReplicationRules, ReplicationVideo, classify

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _v(
    n: int,
    channel: str,
    *,
    weeks: int = 0,
    views: int | None = 100_000,
    subs: int | None = 5_000,
    confidence: str = "HIGH",
    group: str | None = None,
) -> ReplicationVideo:
    return ReplicationVideo(
        video_id=f"V{n}",
        channel_id=channel,
        creator_group=group or channel,
        published_at=START + timedelta(weeks=weeks),
        view_count=views,
        subscriber_count=subs,
        confidence=confidence,
    )


def test_one_viral_video_from_one_channel_is_single_outlier() -> None:
    result = classify([_v(1, "A")])
    assert result["replication_state"] == "SINGLE_OUTLIER"
    assert "ONE_CREATOR_GROUP" in result["reason_codes"]


def test_three_independent_channels_over_three_weeks_is_replicated() -> None:
    videos = [_v(i, c, weeks=w) for i, (c, w) in enumerate([("A", 0), ("B", 1), ("C", 2)])]
    result = classify(videos)
    # Solo 3 videos: ni el reparto de «replicado» ni los 4 videos de «prometedor».
    assert result["replication_state"] == "UNKNOWN"
    assert "REPLICATION_INSUFFICIENT_SAMPLE" in result["reason_codes"]
    six = [_v(i, f"C{i}", weeks=i) for i in range(6)]
    assert classify(six)["replication_state"] == "REPLICATED"


def test_two_videos_per_channel_also_counts_as_spread() -> None:
    videos = [
        _v(1, "A", weeks=0),
        _v(2, "A", weeks=1),
        _v(3, "B", weeks=2),
        _v(4, "B", weeks=2),
        _v(5, "C", weeks=3),
        _v(6, "C", weeks=3),
    ]
    result = classify(videos, ReplicationRules(min_videos_distributed=99))
    assert result["replication_state"] == "REPLICATED"
    assert result["max_videos_per_channel"] == 2


def test_top_channel_concentration_blocks_replicated() -> None:
    videos = [_v(i, "BIG", weeks=i % 3) for i in range(5)]
    videos += [_v(10, "B", weeks=0), _v(11, "C", weeks=1)]
    result = classify(videos)
    assert result["top_channel_concentration"] >= 0.6
    assert result["replication_state"] != "REPLICATED"
    assert result["replication_state"] == "PROMISING"


def test_two_channels_four_videos_two_weeks_is_promising() -> None:
    videos = [_v(1, "A", weeks=0), _v(2, "A", weeks=0), _v(3, "B", weeks=1), _v(4, "B", weeks=1)]
    assert classify(videos)["replication_state"] == "PROMISING"


def test_few_weeks_is_not_replicated() -> None:
    videos = [_v(i, f"C{i}", weeks=0) for i in range(6)]
    result = classify(videos)
    assert result["distinct_weeks"] == 1
    assert result["replication_state"] != "REPLICATED"


def test_mirror_channels_of_one_owner_count_once() -> None:
    videos = [_v(i, f"M{i}", weeks=i, group="OWNER") for i in range(6)]
    result = classify(videos)
    assert result["independent_channels_observed"] == 1
    assert result["replication_state"] == "SINGLE_OUTLIER"


def test_success_in_a_single_video_is_a_single_outlier() -> None:
    videos = [_v(1, "A", views=900_000), _v(2, "B", views=100), _v(3, "C", views=200)]
    result = classify(videos)
    assert result["successful_videos_observed"] == 1
    assert result["replication_state"] == "SINGLE_OUTLIER"


def test_large_channels_do_not_count_as_successes() -> None:
    videos = [_v(i, f"C{i}", weeks=i, subs=2_000_000) for i in range(6)]
    result = classify(videos)
    assert result["successful_videos_observed"] == 0
    assert result["top_channel_concentration"] is None
    assert result["replication_state"] != "REPLICATED"


def test_missing_data_is_unknown_never_zero() -> None:
    videos = [_v(i, f"C{i}", weeks=i, views=None, subs=None) for i in range(6)]
    result = classify(videos)
    assert result["replication_state"] == "UNKNOWN"
    assert "SUCCESS_DATA_MISSING" in result["reason_codes"]


def test_no_videos_is_unknown() -> None:
    result = classify([])
    assert result["replication_state"] == "UNKNOWN"
    assert result["independent_channels_observed"] == 0
    assert result["top_channel_concentration"] is None


def test_low_confidence_annotations_are_excluded_and_reported() -> None:
    videos = [_v(1, "A"), _v(2, "B", confidence="LOW"), _v(3, "C", confidence="LOW")]
    result = classify(videos)
    assert result["relevant_videos_observed"] == 1
    assert result["excluded_low_confidence"] == 2
    assert "LOW_CONFIDENCE_VIDEOS_EXCLUDED" in result["reason_codes"]


def test_same_video_annotated_twice_counts_once() -> None:
    result = classify([_v(1, "A"), _v(1, "A")])
    assert result["relevant_videos_observed"] == 1


def test_result_always_declares_its_limits() -> None:
    result = classify([_v(i, f"C{i}", weeks=i) for i in range(6)])
    assert result["independence_verified"] is False
    assert result["sample_bias_warning"] == "coverage_nonrepresentative"
    assert result["rule_version"] == "repl-v1"
