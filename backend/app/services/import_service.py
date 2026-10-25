"""Importación de archivos JSON/CSV exportados con derecho de reutilización (spec §5.3, §6.1).

- Cada fila se valida con Pydantic: las válidas se guardan y las inválidas se devuelven con motivo.
- Idempotente por (proveedor, idempotency_key): repetir el envío no vuelve a aplicar nada.
- Los datos importados son de terceros: caducan con el mismo plazo que la API (spec §5.5).
"""

import csv
import io
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.db import models as m
from app.providers.base import ChannelRecord, VideoRecord
from app.services.ingestion_service import upsert_channel, upsert_video

IMPORT_SCHEMA_VERSION = "1"
MAX_ROWS = 5_000
MAX_ERRORS_RETURNED = 100
IMPORT_PROVIDERS = ("vidiq_import", "manual_import")
CSV_COLUMNS = (
    "youtube_video_id",
    "youtube_channel_id",
    "channel_title",
    "title",
    "published_at",
    "duration_seconds",
    "default_language",
    "default_audio_language",
    "view_count",
    "subscriber_count",
    "live_broadcast",
)


class ImportRow(BaseModel):
    youtube_video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{6,20}$")
    youtube_channel_id: str = Field(pattern=r"^[A-Za-z0-9_-]{6,40}$")
    channel_title: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    published_at: datetime
    duration_seconds: int | None = Field(default=None, ge=0, le=172_800)
    default_language: str | None = Field(default=None, max_length=12)
    default_audio_language: str | None = Field(default=None, max_length=12)
    view_count: int | None = Field(default=None, ge=0)
    subscriber_count: int | None = Field(default=None, ge=0)
    live_broadcast: Literal["none", "live", "upcoming"] | None = None

    @field_validator("published_at")
    @classmethod
    def _requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("debe incluir zona horaria")
        return value

    @field_validator("title", "channel_title")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("contiene caracteres de control")
        return value


def _csv_rows(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not set(CSV_COLUMNS) <= set(reader.fieldnames):
        raise ProblemError(
            422,
            "CSV_COLUMNS_MISSING",
            "CSV sin columnas requeridas",
            f"Columnas: {', '.join(CSV_COLUMNS)}",
        )
    rows: list[dict[str, Any]] = []
    for raw in reader:
        row: dict[str, Any] = {}
        for key in CSV_COLUMNS:
            value = (raw.get(key) or "").strip()
            row[key] = value if value != "" else None
        for numeric in ("duration_seconds", "view_count", "subscriber_count"):
            if row[numeric] is not None:
                row[numeric] = _to_int(row[numeric])
        rows.append(row)
    return rows


def _to_int(value: str) -> Any:
    try:
        return int(value)
    except ValueError:
        return value  # Pydantic rechazará el valor con un mensaje por fila.


def _previous_import(session: Session, object_id: str) -> m.AuditEvent | None:
    return session.scalars(
        select(m.AuditEvent).where(
            m.AuditEvent.event_type == "IMPORT_APPLIED", m.AuditEvent.object_id == object_id
        )
    ).first()


def import_rows(
    session: Session,
    settings: Settings,
    *,
    provider: str,
    idempotency_key: str,
    license_confirmed: bool,
    source_schema_version: str,
    rows: list[dict[str, Any]] | None = None,
    csv_text: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if source_schema_version != IMPORT_SCHEMA_VERSION:
        raise ProblemError(
            422, "SCHEMA_VERSION", "Versión de esquema no soportada", IMPORT_SCHEMA_VERSION
        )
    if not license_confirmed:
        raise ProblemError(
            422,
            "LICENSE_NOT_CONFIRMED",
            "Confirme que tiene derecho a reutilizar estos datos",
            "Sin esa confirmación no se importa nada.",
        )
    if provider not in IMPORT_PROVIDERS:
        raise ProblemError(422, "PROVIDER_NOT_ALLOWED", "Proveedor de importación no permitido")

    object_id = f"{provider}:{idempotency_key}"
    previous = _previous_import(session, object_id)
    if previous is not None:
        return {**previous.details_redacted_json, "idempotent_replay": True}

    raw_rows = _csv_rows(csv_text) if csv_text is not None else (rows or [])
    if len(raw_rows) > MAX_ROWS:
        raise ProblemError(
            422, "TOO_MANY_ROWS", "Demasiadas filas", f"Máximo {MAX_ROWS} por archivo."
        )

    applied_at = now or datetime.now(UTC)
    accepted = 0
    errors: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            row = ImportRow.model_validate(raw)
        except ValidationError as exc:
            for issue in exc.errors():
                if len(errors) < MAX_ERRORS_RETURNED:
                    errors.append(
                        {
                            "row": index + 1,
                            "field": ".".join(str(p) for p in issue["loc"]),
                            "message": issue["msg"],
                        }
                    )
            continue
        _apply_row(session, settings, row, provider=provider, now=applied_at)
        accepted += 1

    summary: dict[str, Any] = {
        "provider": provider,
        "idempotency_key": idempotency_key,
        "source_schema_version": source_schema_version,
        "received": len(raw_rows),
        "accepted": accepted,
        "rejected": len(raw_rows) - accepted,
        "errors": errors,
        "idempotent_replay": False,
    }
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=None,
            actor="local_owner",
            event_type="IMPORT_APPLIED",
            object_type="import",
            object_id=object_id,
            details_redacted_json=summary,
        )
    )
    session.flush()
    return summary


def _apply_row(
    session: Session, settings: Settings, row: ImportRow, *, provider: str, now: datetime
) -> None:
    hidden = row.subscriber_count is None
    channel = upsert_channel(
        session,
        ChannelRecord(
            youtube_channel_id=row.youtube_channel_id,
            title=row.channel_title,
            subscriber_count=row.subscriber_count,
            hidden_subscribers=hidden,
            uploads_playlist_id=None,
            country=None,
        ),
        run_id=None,
        now=now,
        settings=settings,
        source_data_type="PROVIDER",
        provider=provider,
    )
    upsert_video(
        session,
        VideoRecord(
            youtube_video_id=row.youtube_video_id,
            youtube_channel_id=row.youtube_channel_id,
            title=row.title,
            published_at=row.published_at.isoformat(),
            duration_iso=None if row.duration_seconds is None else f"PT{row.duration_seconds}S",
            default_language=row.default_language,
            default_audio_language=row.default_audio_language,
            view_count=row.view_count,
            live_broadcast=row.live_broadcast,
        ),
        channel,
        run_id=None,
        now=now,
        settings=settings,
        source_data_type="PROVIDER",
        provider=provider,
    )
