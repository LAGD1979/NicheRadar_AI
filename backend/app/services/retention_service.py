"""Purga de datos de terceros caducados (spec §5.5, T16).

Un dato no autorizado por el dueño se elimina o refresca antes del plazo. Aquí se purga:
los valores observados se borran (quedan en NULL, nunca en 0) y el registro se marca EXPIRED.
La UI muestra «Caducada». La purga deja una auditoría sin valores.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m

EXPIRED_TITLE = "[Dato caducado]"


def purge_expired(session: Session, now: datetime) -> dict[str, int]:
    videos = session.scalars(
        select(m.Video).where(
            m.Video.retention_deadline.is_not(None),
            m.Video.retention_deadline < now,
            m.Video.owner_authorized.is_(False),
            m.Video.availability != "EXPIRED",
        )
    ).all()
    for video in videos:
        video.availability = "EXPIRED"
        video.title = EXPIRED_TITLE
        video.view_count = None
        video.duration_seconds = None
        video.url = None
        video.provider_metrics = None
        video.video_type = "UNKNOWN"
        video.video_type_evidence = "Dato caducado y purgado"

    channels = session.scalars(
        select(m.Channel).where(
            m.Channel.retention_deadline.is_not(None),
            m.Channel.retention_deadline < now,
            m.Channel.owner_authorized.is_(False),
            m.Channel.subscriber_band != "EXPIRED",
        )
    ).all()
    for channel in channels:
        channel.title_current = EXPIRED_TITLE
        channel.subscriber_count = None
        channel.subscriber_band = "EXPIRED"
        channel.uploads_playlist_id = None

    counts = {"videos_expired": len(videos), "channels_expired": len(channels)}
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=None,
            actor="system",
            event_type="RETENTION_PURGE",
            object_type="retention",
            object_id=now.isoformat(),
            details_redacted_json=counts,
        )
    )
    session.flush()
    return counts
