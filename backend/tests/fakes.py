"""Fuente falsa de YouTube para pruebas. No hace red. Datos rotulados como SINTÉTICOS."""

from app.providers.base import (
    ChannelRecord,
    ProviderError,
    SearchHit,
    SearchParams,
    VideoRecord,
)


class FakeSource:
    """Implementa el contrato DiscoverySource con datos fijos y contadores de llamadas."""

    def __init__(
        self,
        *,
        hits: dict[str, list[SearchHit]] | None = None,
        videos: list[VideoRecord] | None = None,
        channels: list[ChannelRecord] | None = None,
        upload_ids: list[str] | None = None,
        search_error: ProviderError | None = None,
        second_page: bool = False,
    ) -> None:
        self.hits = hits or {}
        self.videos_data = videos or []
        self.channels_data = channels or []
        self.upload_ids = upload_ids or []
        self.search_error = search_error
        self.second_page = second_page
        self.endpoints: list[str] = []
        self.search_params: list[SearchParams] = []
        self.closed = False

    def search(self, params: SearchParams) -> tuple[list[SearchHit], str | None]:
        self.endpoints.append("search")
        self.search_params.append(params)
        if self.search_error is not None:
            raise self.search_error
        if self.second_page and params.page_token is None:
            return self.hits.get(params.query, []), "PAGE-2"
        if self.second_page:
            return [], None
        return self.hits.get(params.query, []), None

    def videos(self, ids: list[str]) -> list[VideoRecord]:
        self.endpoints.append("videos")
        return [v for v in self.videos_data if v.youtube_video_id in ids]

    def channels(self, ids: list[str]) -> list[ChannelRecord]:
        self.endpoints.append("channels")
        return [c for c in self.channels_data if c.youtube_channel_id in ids]

    def uploads(
        self, playlist_id: str, page_token: str | None = None
    ) -> tuple[list[str], str | None]:
        self.endpoints.append("playlistItems")
        return list(self.upload_ids), None

    def close(self) -> None:
        self.closed = True


def synthetic_video(
    video_id: str,
    channel_id: str,
    *,
    duration_iso: str | None = "PT12M",
    audio: str | None = "pt",
    meta: str | None = None,
    views: int | None = 1200,
    live: str | None = "none",
    published: str = "2026-10-01T12:00:00Z",
) -> VideoRecord:
    return VideoRecord(
        youtube_video_id=video_id,
        youtube_channel_id=channel_id,
        title=f"[SINTÉTICO] {video_id}",
        published_at=published,
        duration_iso=duration_iso,
        default_language=meta,
        default_audio_language=audio,
        view_count=views,
        live_broadcast=live,
    )


def synthetic_channel(
    channel_id: str,
    *,
    subs: int | None = 1500,
    hidden: bool = False,
    uploads: str | None = "UU-SYN",
) -> ChannelRecord:
    return ChannelRecord(
        youtube_channel_id=channel_id,
        title=f"Canal Sintético {channel_id}",
        subscriber_count=subs,
        hidden_subscribers=hidden,
        uploads_playlist_id=uploads,
        country=None,
    )


def synthetic_hit(video_id: str, channel_id: str) -> SearchHit:
    return SearchHit(
        youtube_video_id=video_id,
        youtube_channel_id=channel_id,
        published_at="2026-10-01T12:00:00Z",
        title=f"[SINTÉTICO] {video_id}",
    )
