"""Adaptador oficial de YouTube Data API v3 (spec §5.2).

- Solo métodos oficiales: search.list, videos.list, channels.list, playlistItems.list.
- La clave viaja como parámetro y nunca aparece en mensajes de error ni en logs.
- Coste en unidades de cuota: search.list = 100; videos/channels/playlistItems = 1.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.providers.base import (
    ChannelRecord,
    InvalidRequest,
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderUnavailable,
    QuotaExhausted,
    SearchHit,
    SearchParams,
    VideoRecord,
)

UNITS = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1}
BATCH_SIZE = 50
QUOTA_REASONS = {
    "quotaExceeded",
    "dailyLimitExceeded",
    "rateLimitExceeded",
    "userRateLimitExceeded",
}
AUTH_REASONS = {"forbidden", "accessNotConfigured", "keyInvalid", "keyExpired", "ipRefererBlocked"}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _reason(response: httpx.Response) -> str:
    try:
        errors = response.json()["error"]["errors"]
        return str(errors[0]["reason"])
    except (KeyError, IndexError, TypeError, ValueError):
        return "unknown"


class YouTubeOfficialClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ProviderNotConfigured("Falta YOUTUBE_API_KEY.")
        self._api_key = api_key
        self._max_retries = max_retries
        self._sleep = sleep
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {**params, "key": self._api_key}
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._http.get(f"/{endpoint}", params=query)
            except httpx.TimeoutException as exc:
                if attempt <= self._max_retries:
                    self._sleep(2.0**attempt)
                    continue
                raise ProviderUnavailable(f"{endpoint}: tiempo de espera agotado") from exc
            if response.status_code < 400:
                payload: dict[str, Any] = response.json()
                return payload
            reason = _reason(response)
            if response.status_code == 403 and reason in QUOTA_REASONS:
                raise QuotaExhausted(f"{endpoint}: cuota diaria agotada ({reason})")
            if response.status_code in (401, 403) or reason in AUTH_REASONS:
                raise ProviderAuthError(f"{endpoint}: credencial o permiso rechazado ({reason})")
            if response.status_code in RETRYABLE_STATUS and attempt <= self._max_retries:
                self._sleep(2.0**attempt)
                continue
            if response.status_code in RETRYABLE_STATUS:
                raise ProviderUnavailable(f"{endpoint}: HTTP {response.status_code}")
            raise InvalidRequest(f"{endpoint}: HTTP {response.status_code} ({reason})")

    def search(self, params: SearchParams) -> tuple[list[SearchHit], str | None]:
        query: dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "q": params.query,
            "maxResults": params.max_results,
            "order": "relevance",
        }
        if params.published_after:
            query["publishedAfter"] = params.published_after
        if params.published_before:
            query["publishedBefore"] = params.published_before
        if params.relevance_language:
            query["relevanceLanguage"] = params.relevance_language
        if params.region_code:
            query["regionCode"] = params.region_code
        if params.page_token:
            query["pageToken"] = params.page_token
        data = self._get("search", query)
        hits = [parse_search_item(item) for item in data.get("items", [])]
        return [h for h in hits if h is not None], data.get("nextPageToken")

    def videos(self, ids: list[str]) -> list[VideoRecord]:
        records: list[VideoRecord] = []
        for start in range(0, len(ids), BATCH_SIZE):
            batch = ids[start : start + BATCH_SIZE]
            data = self._get(
                "videos",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(batch),
                    "maxResults": BATCH_SIZE,
                },
            )
            records.extend(r for r in (parse_video_item(i) for i in data.get("items", [])) if r)
        return records

    def channels(self, ids: list[str]) -> list[ChannelRecord]:
        records: list[ChannelRecord] = []
        for start in range(0, len(ids), BATCH_SIZE):
            batch = ids[start : start + BATCH_SIZE]
            data = self._get(
                "channels",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(batch),
                    "maxResults": BATCH_SIZE,
                },
            )
            records.extend(r for r in (parse_channel_item(i) for i in data.get("items", [])) if r)
        return records

    def uploads(
        self, playlist_id: str, page_token: str | None = None
    ) -> tuple[list[str], str | None]:
        """Lista de uploads del canal (T06): playlistItems, nunca search.list por canal."""
        params: dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": BATCH_SIZE,
        }
        if page_token:
            params["pageToken"] = page_token
        data = self._get("playlistItems", params)
        ids = [
            str(i["contentDetails"]["videoId"])
            for i in data.get("items", [])
            if "contentDetails" in i
        ]
        return ids, data.get("nextPageToken")


def parse_search_item(item: dict[str, Any]) -> SearchHit | None:
    video_id = (item.get("id") or {}).get("videoId")
    snippet = item.get("snippet") or {}
    channel_id = snippet.get("channelId")
    if not video_id or not channel_id:
        return None
    return SearchHit(
        youtube_video_id=str(video_id),
        youtube_channel_id=str(channel_id),
        published_at=str(snippet.get("publishedAt", "")),
        title=str(snippet.get("title", "")),
    )


def parse_video_item(item: dict[str, Any]) -> VideoRecord | None:
    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    stats = item.get("statistics") or {}
    if not item.get("id") or not snippet.get("channelId"):
        return None
    view_raw = stats.get("viewCount")
    return VideoRecord(
        youtube_video_id=str(item["id"]),
        youtube_channel_id=str(snippet["channelId"]),
        title=str(snippet.get("title", "")),
        published_at=str(snippet.get("publishedAt", "")),
        duration_iso=content.get("duration"),
        default_language=snippet.get("defaultLanguage"),
        default_audio_language=snippet.get("defaultAudioLanguage"),
        view_count=int(view_raw) if view_raw is not None and str(view_raw).isdigit() else None,
        live_broadcast=snippet.get("liveBroadcastContent"),
    )


def parse_channel_item(item: dict[str, Any]) -> ChannelRecord | None:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}
    if not item.get("id"):
        return None
    hidden = bool(stats.get("hiddenSubscriberCount", False))
    subs_raw = stats.get("subscriberCount")
    subscribers: int | None = None
    if not hidden and subs_raw is not None and str(subs_raw).isdigit():
        subscribers = int(subs_raw)  # 0 real se conserva; ocultos → None (T02)
    uploads = (content.get("relatedPlaylists") or {}).get("uploads")
    return ChannelRecord(
        youtube_channel_id=str(item["id"]),
        title=str(snippet.get("title", "")),
        subscriber_count=subscribers,
        hidden_subscribers=hidden,
        uploads_playlist_id=str(uploads) if uploads else None,
        country=snippet.get("country"),
    )
