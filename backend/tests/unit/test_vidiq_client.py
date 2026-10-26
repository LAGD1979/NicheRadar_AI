"""Cliente vidIQ MCP con transporte simulado: ninguna prueba sale a la red."""

import json
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
from app.providers.vidiq_mcp import OutlierParams, VidIQClient

KEY = "vidiq-TEST-NO-REAL-0123456789"
URL = "https://mcp.test/mcp"


def _video(**over: Any) -> dict[str, Any]:
    base = {
        "videoId": "AbCdEf12345",
        "videoTitle": "[SINTÉTICO] video",
        "videoPublishedAt": 1791006046,
        "videoDuration": 1388,
        "channelId": "UCsynthetic0000000001",
        "channelTitle": "Canal sintético",
        "channelCountry": "PK",
        "subscriberCount": 68600,
        "viewCount": 410787,
        "breakoutScore": 2.42,
        "vph": 0.33,
        "engagementRate": 0.008,
        "videoType": "long",
        "trendCategories": None,
        "hasAiLabel": None,
        "videoTags": ["no se conserva"],
    }
    return {**base, **over}


def _sse(result: dict[str, Any]) -> httpx.Response:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})
    return httpx.Response(
        200,
        text=f"event: message\ndata: {payload}\n\n",
        headers={"content-type": "text/event-stream"},
    )


def _client(handler: Any, retries: int = 3) -> VidIQClient:
    return VidIQClient(
        api_key=KEY,
        url=URL,
        max_retries=retries,
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )


def test_no_key_means_not_configured() -> None:
    with pytest.raises(ProviderNotConfigured):
        VidIQClient(api_key="", url=URL)


def test_outliers_sends_bearer_and_parses_structured_data() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _sse(
            {
                "content": [{"type": "text", "text": "Found 1"}],
                "_meta": {"widgetData": {"videos": [_video()]}},
            }
        )

    videos, skipped = _client(handler).outliers(
        OutlierParams(language="en", trend_categories=("video_essay",), max_subscribers=100000)
    )
    request = seen[0]
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "vidiq_outliers"
    arguments = body["params"]["arguments"]
    assert arguments["trendCategories"] == ["video_essay"]
    assert arguments["maxSubscribers"] == 100000
    assert "keyword" not in arguments  # sin tema: nada que sesgue la búsqueda
    assert skipped == 0
    video = videos[0]
    assert video.youtube_video_id == "AbCdEf12345"
    assert video.breakout_score == 2.42
    assert video.published_at.startswith("2026-")
    assert not hasattr(video, "tags")


def test_invalid_record_is_skipped_and_counted() -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        bad = _video(videoId="x")  # id demasiado corto
        return _sse({"_meta": {"widgetData": {"videos": [bad, _video()]}}})

    videos, skipped = _client(handler).outliers(OutlierParams())
    assert len(videos) == 1
    assert skipped == 1


def test_empty_result_and_unexpected_format() -> None:
    empty = _client(lambda _r: _sse({"content": [{"type": "text", "text": "No results found"}]}))
    assert empty.outliers(OutlierParams()) == ([], 0)
    odd = _client(lambda _r: _sse({"content": [{"type": "text", "text": "algo raro"}]}))
    with pytest.raises(InvalidRequest):
        odd.outliers(OutlierParams())


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_do_not_leak_key(status: int) -> None:
    client = _client(lambda _r: httpx.Response(status))
    with pytest.raises(ProviderAuthError) as info:
        client.outliers(OutlierParams())
    assert KEY not in str(info.value)


def test_credit_error_is_quota_exhausted() -> None:
    client = _client(
        lambda _r: _sse(
            {"isError": True, "content": [{"type": "text", "text": "Insufficient credits"}]}
        )
    )
    with pytest.raises(QuotaExhausted):
        client.outliers(OutlierParams())


def test_transient_errors_are_retried_then_unavailable() -> None:
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ProviderUnavailable):
        _client(handler, retries=3).outliers(OutlierParams())
    assert calls["n"] == 3


def test_retry_recovers_after_429() -> None:
    calls = {"n": 0}

    def handler(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return _sse({"_meta": {"widgetData": {"videos": [_video()]}}})

    videos, _ = _client(handler).outliers(OutlierParams())
    assert len(videos) == 1 and calls["n"] == 2


def test_balance_reads_structured_content() -> None:
    client = _client(lambda _r: _sse({"structuredContent": {"totalCredits": 2014}}))
    assert client.balance() == 2014
