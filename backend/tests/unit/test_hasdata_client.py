"""Cliente de HasData con transporte simulado (formas de respuesta observadas en vivo)."""

from typing import Any

import httpx
import pytest

from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderUnavailable,
    QuotaExhausted,
)
from app.providers.hasdata import HasDataClient

KEY = "hasdata-TEST-NO-REAL-0123456789"
BASE = "https://api.test"


def _timeline(values: list[tuple[str, int | None, bool]]) -> dict[str, Any]:
    return {
        "requestMetadata": {"status": "ok"},
        "interestOverTime": {
            "timelineData": [
                {
                    "date": "semana",
                    "timestamp": ts,
                    "isPartial": partial,
                    "values": [
                        {
                            "query": "q",
                            "value": "" if v is None else str(v),
                            "extractedValue": 0 if v is None else v,
                            "hasData": v is not None,
                        }
                    ],
                }
                for ts, v, partial in values
            ]
        },
    }


def _client(handler: Any, retries: int = 3) -> HasDataClient:
    return HasDataClient(
        api_key=KEY,
        base_url=BASE,
        max_retries=retries,
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )


def test_no_key_means_not_configured() -> None:
    with pytest.raises(ProviderNotConfigured):
        HasDataClient(api_key="")


def test_timeseries_sends_key_in_header_and_the_expected_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json=_timeline([("1761436800", 43, False), ("1792886400", 52, True)])
        )

    points = _client(handler).interest_over_time("video ensayo", geo="MX")
    request = seen[0]
    assert request.headers["x-api-key"] == KEY
    assert request.url.path == "/scrape/google-trends/search"
    assert request.url.params["q"] == "video ensayo"
    assert request.url.params["geo"] == "MX"
    assert request.url.params["gprop"] == "youtube"
    assert request.url.params["dataType"] == "timeseries"
    assert [p.value for p in points] == [43, 52]
    assert [p.partial for p in points] == [False, True]
    assert points[0].timestamp.year == 2025


def test_weeks_without_data_are_unknown_not_zero() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_timeline([("1761436800", None, False)]))

    points = _client(handler).interest_over_time("tema muy raro")
    assert points[0].value is None


def test_worldwide_search_omits_geo_and_gprop_when_empty() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_timeline([("1761436800", 10, False)]))

    _client(handler).interest_over_time("x", gprop="")
    assert "geo" not in seen[0].url.params
    assert "gprop" not in seen[0].url.params


def test_related_queries_are_parsed_in_both_lists() -> None:
    body = {
        "requestMetadata": {"status": "ok"},
        "relatedQueries": {
            "rising": [{"query": "nuevo", "value": "Breakout", "extractedValue": 5000}],
            "top": [{"query": "videos", "value": "100", "extractedValue": 100}],
        },
    }
    related = _client(lambda _r: httpx.Response(200, json=body)).related_queries("video ensayo")
    assert [(r.kind, r.query, r.value) for r in related] == [
        ("top", "videos", 100),
        ("rising", "nuevo", 5000),
    ]


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_do_not_leak_the_key(status: int) -> None:
    with pytest.raises(ProviderAuthError) as info:
        _client(lambda _r: httpx.Response(status)).interest_over_time("x")
    assert KEY not in str(info.value)


def test_payment_required_means_credits_exhausted() -> None:
    with pytest.raises(QuotaExhausted):
        _client(lambda _r: httpx.Response(402)).interest_over_time("x")


def test_transient_errors_are_retried_then_unavailable() -> None:
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ProviderUnavailable):
        _client(handler, retries=3).interest_over_time("x")
    assert calls["n"] == 3


def test_retry_recovers_after_a_429() -> None:
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=_timeline([("1761436800", 20, False)]))

    assert len(_client(handler).interest_over_time("x")) == 1
    assert calls["n"] == 2


def test_bad_input_and_unexpected_bodies_are_invalid_requests() -> None:
    client = _client(lambda _r: httpx.Response(200, json={"requestMetadata": {"status": "ok"}}))
    with pytest.raises(InvalidRequest):
        client.interest_over_time("   ")
    with pytest.raises(InvalidRequest):
        client.interest_over_time("x", date="hace mucho")
    with pytest.raises(InvalidRequest):
        client.interest_over_time("x", gprop="otra")
    with pytest.raises(InvalidRequest):
        client.interest_over_time("x")  # sin serie temporal en la respuesta
    failed = _client(lambda _r: httpx.Response(200, json={"requestMetadata": {"status": "error"}}))
    with pytest.raises(InvalidRequest):
        failed.interest_over_time("x")
    not_json = _client(lambda _r: httpx.Response(200, text="<html>"))
    with pytest.raises(InvalidRequest):
        not_json.interest_over_time("x")
