import pytest

from app.domain.classification import (
    classify_language,
    classify_video_type,
    parse_count,
    parse_iso_duration,
    primary_language,
)


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [
        ("PT1H2M3S", 3723),
        ("PT45S", 45),
        ("P1D", 86_400),
        ("PT0S", 0),
        (None, None),
        ("", None),
        ("PX", None),
        ("P", None),
    ],
)
def test_iso_duration_to_seconds(raw: str | None, seconds: int | None) -> None:
    assert parse_iso_duration(raw) == seconds


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pt-BR", "pt"),
        ("en", "en"),
        ("zh-Hans", "zh-Hans"),
        ("zh-Hant-TW", "zh-Hant"),
        (None, None),
        ("", None),
    ],
)
def test_primary_language_keeps_chinese_variants(raw: str | None, expected: str | None) -> None:
    assert primary_language(raw) == expected


def test_declared_audio_language_wins_over_metadata() -> None:
    verdict = classify_language(default_audio="pt", default_metadata="pt")
    assert (verdict.state, verdict.confidence) == ("pt", "HIGH")


def test_language_conflict_is_unknown_not_forced() -> None:
    # T04: el título dice una cosa y el audio otra: no se fuerza ningún idioma.
    verdict = classify_language(default_audio="pt", default_metadata="en")
    assert (verdict.state, verdict.confidence) == ("UNKNOWN", "CONFLICT")


def test_metadata_only_is_medium_confidence() -> None:
    verdict = classify_language(default_audio=None, default_metadata="fr-CA")
    assert (verdict.state, verdict.confidence) == ("fr", "MEDIUM")


def test_no_language_signal_is_unknown_none() -> None:
    verdict = classify_language(None, None)
    assert (verdict.state, verdict.confidence) == ("UNKNOWN", "NONE")


def test_short_ambiguous_duration_is_unknown() -> None:
    # Un video de 100 s no se clasifica como Short ni como largo sin evidencia (spec §0.5).
    assert classify_video_type(100, "none").video_type == "UNKNOWN"


def test_long_video_over_threshold() -> None:
    assert classify_video_type(720, "none").video_type == "LONG"


def test_live_content_is_live() -> None:
    assert classify_video_type(3000, "live").video_type == "LIVE"


def test_missing_duration_is_unknown() -> None:
    assert classify_video_type(None, "none").video_type == "UNKNOWN"


@pytest.mark.parametrize(
    ("raw", "value"), [(None, None), ("0", 0), ("1500", 1500), ("x", None), (-3, None)]
)
def test_counts_never_turn_missing_into_zero(raw: str | int | None, value: int | None) -> None:
    assert parse_count(raw) == value
