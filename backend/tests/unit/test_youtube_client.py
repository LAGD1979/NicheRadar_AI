"""Cliente de YouTube con transporte simulado: ninguna prueba sale a la red."""

import httpx
import pytest

from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderUnavailable,
    QuotaExhausted,
    SearchParams,
)
from app.providers.youtube_official import (
    YouTubeOfficialClient,
    parse_channel_item,
    parse_video_item,
)

KEY = "TEST-KEY-NO-REAL-0123456789"


def make_client(
    handler, *, retries: int = 3, sleeps: list[float] | None = None
) -> YouTubeOfficialClient:
    record = sleeps if sleeps is not None else []
    return YouTubeOfficialClient(
        api_key=KEY,
        base_url="https://example.invalid/youtube/v3",
        timeout=5,
        max_retries=retries,
        transport=httpx.MockTransport(handler),
        sleep=record.append,
    )


def error_body(reason: str, status_message: str = "x") -> dict[str, object]:
    return {"error": {"code": 403, "message": status_message, "errors": [{"reason": reason}]}}


def test_search_sends_window_and_language_and_returns_next_page() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "SYNV01"},
                        "snippet": {
                            "channelId": "SYNCH01",
                            "publishedAt": "2026-10-01T00:00:00Z",
                            "title": "t",
                        },
                    }
                ],
                "nextPageToken": "PAGE2",
            },
        )

    client = make_client(handler)
    hits, token = client.search(
        SearchParams(
            query="historia",
            published_after="2026-09-01T00:00:00Z",
            published_before=None,
            relevance_language="es",
            region_code="CL",
        )
    )
    assert [h.youtube_video_id for h in hits] == ["SYNV01"]
    assert token == "PAGE2"
    params = seen[0].url.params
    assert params["type"] == "video"
    assert params["relevanceLanguage"] == "es"
    assert params["publishedAfter"] == "2026-09-01T00:00:00Z"
    assert "publishedBefore" not in params


def test_quota_403_maps_to_paused_quota_and_never_leaks_key() -> None:
    client = make_client(lambda r: httpx.Response(403, json=error_body("quotaExceeded")))
    with pytest.raises(QuotaExhausted) as info:
        client.search(
            SearchParams(
                query="x",
                published_after=None,
                published_before=None,
                relevance_language=None,
                region_code=None,
            )
        )
    assert KEY not in str(info.value)


def test_forbidden_403_is_auth_error_not_quota() -> None:
    client = make_client(lambda r: httpx.Response(403, json=error_body("forbidden")))
    with pytest.raises(ProviderAuthError):
        client.videos(["SYNV01"])


def test_invalid_key_is_auth_error_without_retry() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json=error_body("keyInvalid"))

    client = make_client(handler)
    with pytest.raises(ProviderAuthError):
        client.videos(["SYNV01"])
    assert len(calls) == 1


def test_400_invalid_request_is_definitive_without_retry() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json=error_body("invalidParameter"))

    client = make_client(handler)
    with pytest.raises(InvalidRequest):
        client.videos(["SYNV01"])
    assert len(calls) == 1


def test_transient_500_is_retried_with_backoff_then_succeeds() -> None:
    sleeps: list[float] = []
    responses = iter(
        [httpx.Response(500), httpx.Response(503), httpx.Response(200, json={"items": []})]
    )
    client = make_client(lambda r: next(responses), sleeps=sleeps)
    assert client.videos(["SYNV01"]) == []
    assert sleeps == [2.0, 4.0]


def test_exhausted_retries_become_unavailable() -> None:
    client = make_client(lambda r: httpx.Response(503), retries=2)
    with pytest.raises(ProviderUnavailable):
        client.channels(["SYNCH01"])


def test_timeouts_retry_then_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler, retries=1)
    with pytest.raises(ProviderUnavailable):
        client.videos(["SYNV01"])


def test_uploads_use_playlist_items_not_search() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(
            200,
            json={"items": [{"contentDetails": {"videoId": "SYNV09"}}], "nextPageToken": None},
        )

    client = make_client(handler)
    ids, token = client.uploads("UU-SYNTHETIC")
    assert ids == ["SYNV09"]
    assert token is None
    assert seen == ["/youtube/v3/playlistItems"]


def test_client_refuses_to_start_without_key() -> None:
    with pytest.raises(ProviderNotConfigured):
        YouTubeOfficialClient(
            api_key="", base_url="https://example.invalid", timeout=1, max_retries=0
        )


def test_hidden_subscribers_are_null_and_zero_is_kept() -> None:
    hidden = parse_channel_item(
        {
            "id": "SYNCH05",
            "snippet": {"title": "t"},
            "statistics": {"hiddenSubscriberCount": True, "subscriberCount": "0"},
        }
    )
    zero = parse_channel_item(
        {"id": "SYNCH04", "snippet": {"title": "t"}, "statistics": {"subscriberCount": "0"}}
    )
    assert hidden is not None and hidden.subscriber_count is None
    assert zero is not None and zero.subscriber_count == 0


def test_missing_view_count_is_null_not_zero() -> None:
    record = parse_video_item(
        {
            "id": "SYNV11",
            "snippet": {
                "channelId": "SYNCH04",
                "title": "t",
                "publishedAt": "2026-10-01T00:00:00Z",
            },
            "contentDetails": {"duration": "PT18M"},
            "statistics": {},
        }
    )
    assert record is not None and record.view_count is None
