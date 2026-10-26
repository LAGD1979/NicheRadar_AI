"""Revisión asistida de competidores (D-64).

La IA propone una calidad para cada video en español sin revisar; una persona acepta o corrige.
- La sugerencia vive en columnas `ai_*` y **nunca** cuenta como revisión ni cambia la saturación.
- Aceptar sugerencias en bloque es una acción humana explícita, con auditoría y con un mínimo de
  confianza; queda marcada como aceptación de la IA para poder medir su precisión.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.db import models as m
from app.domain import competitor_review as cr
from app.prompts import competitor_review_v1 as prompt
from app.providers.ai import AIClient
from app.providers.base import ProviderAuthError, ProviderError, ResponseTruncated
from app.services import spanish_service

BATCH_SIZE = 20
MAX_BATCHES = 10
BULK_SUFFIX = " (aceptó sugerencia IA)"


@dataclass
class ClassifyOutcome:
    batches: int = 0
    suggested: int = 0
    pending_left: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "COMPLETED"


def _pending_rows(
    session: Session, opportunity_id: str
) -> list[tuple[m.DiscoveryMatch, m.Video, m.Channel]]:
    """Un renglón por video en español sin revisar y sin sugerencia."""
    rows = session.execute(
        select(m.DiscoveryMatch, m.Video, m.Channel)
        .join(m.Video, m.Video.id == m.DiscoveryMatch.video_id)
        .join(m.Channel, m.Channel.id == m.Video.channel_id)
        .where(
            m.DiscoveryMatch.opportunity_id == opportunity_id,
            m.DiscoveryMatch.is_spanish_market.is_(True),
            m.DiscoveryMatch.match_quality == "UNREVIEWED",
            m.DiscoveryMatch.ai_quality.is_(None),
            m.Video.availability != "EXPIRED",
        )
        .order_by(m.DiscoveryMatch.position, m.DiscoveryMatch.id)
    ).all()
    unique: dict[str, tuple[m.DiscoveryMatch, m.Video, m.Channel]] = {}
    for match, video, channel in rows:
        unique.setdefault(video.id, (match, video, channel))
    return list(unique.values())


def pending_count(session: Session, opportunity_id: str) -> int:
    return len(_pending_rows(session, opportunity_id))


def context_for(session: Session, opportunity_id: str) -> dict[str, Any]:
    opportunity = session.get(m.Opportunity, opportunity_id)
    if opportunity is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    niche = session.get(m.Niche, opportunity.niche_id)
    fmt = session.get(m.Format, opportunity.format_id)
    plan = session.scalars(
        select(m.SpanishSearchPlan)
        .where(
            m.SpanishSearchPlan.opportunity_id == opportunity_id,
            m.SpanishSearchPlan.status == "APPROVED",
        )
        .order_by(m.SpanishSearchPlan.created_at.desc())
    ).first()
    plan_json = plan.plan_json if plan else {}
    return {
        "nicho": niche.canonical_name_es if niche else "",
        "definicion_nicho": niche.definition if niche else "",
        "formato": fmt.canonical_name_es if fmt else "",
        "estructura_formato": fmt.story_structure if fmt else "",
        "mismo_formato_segun_plan": plan_json.get("same_format_definition"),
        "adyacente_pero_distinto": plan_json.get("adjacent_but_distinct", []),
        "tipo_video": opportunity.video_type,
    }


def classify(
    session: Session,
    client: AIClient,
    opportunity_id: str,
    *,
    run_id: str | None,
    now: datetime,
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES,
) -> ClassifyOutcome:
    result = ClassifyOutcome()
    context = context_for(session, opportunity_id)
    pending = _pending_rows(session, opportunity_id)
    Chunk = list[tuple[m.DiscoveryMatch, m.Video, m.Channel]]

    def apply(chunk: Chunk, suggestions: list[cr.Suggestion]) -> None:
        by_id = {s.source_id: s for s in suggestions}
        for _match, video, _channel in chunk:
            suggestion = by_id.get(f"V:{video.youtube_video_id}")
            if suggestion is None:
                continue
            for sibling in session.scalars(
                select(m.DiscoveryMatch).where(
                    m.DiscoveryMatch.video_id == video.id,
                    m.DiscoveryMatch.opportunity_id == opportunity_id,
                )
            ):
                sibling.ai_quality = suggestion.quality
                sibling.ai_confidence = suggestion.confidence
                sibling.ai_reason = suggestion.reason
                sibling.ai_model = client.model
                sibling.ai_prompt_version = prompt.PROMPT_VERSION
                sibling.ai_suggested_at = now
            result.suggested += 1
        session.flush()

    def run(chunk: Chunk, depth: int = 0) -> bool:
        """Clasifica un lote. Devuelve False si hay que detener todo (clave rechazada)."""
        videos = [
            {
                "source_id": f"V:{video.youtube_video_id}",
                "titulo": video.title,
                "canal": channel.title_current,
                "duracion_minutos": None
                if video.duration_seconds is None
                else round(video.duration_seconds / 60, 1),
                "idioma_verificado": video.language_state,
            }
            for _match, video, channel in chunk
        ]
        allowed = {f"V:{video.youtube_video_id}" for _m, video, _c in chunk}
        result.batches += 1
        try:
            raw = client.complete(prompt.SYSTEM, prompt.build_user_message(context, videos))
        except ProviderAuthError as exc:
            result.outcome = "FAILED"
            result.errors.append({"code": exc.code, "detail": str(exc)})
            return False
        except ResponseTruncated:
            # La respuesta no cupo en el límite de la IA: se parte el lote y se reintenta una vez.
            if len(chunk) > 1 and depth < 2:
                half = len(chunk) // 2
                return run(chunk[:half], depth + 1) and run(chunk[half:], depth + 1)
            result.outcome = "PARTIAL"
            result.errors.append({"code": "RESPONSE_TRUNCATED", "detail": "Respuesta truncada."})
            return True
        except ProviderError as exc:
            result.outcome = "PARTIAL"
            result.errors.append({"code": exc.code, "detail": f"lote {result.batches}: {exc}"})
            return True
        suggestions, error = cr.parse(raw, allowed)
        if error is not None:
            result.outcome = "PARTIAL"
            result.errors.append({"code": error, "detail": f"lote {result.batches} descartado"})
            return True
        apply(chunk, suggestions)
        return True

    for start in range(0, min(len(pending), batch_size * max_batches), batch_size):
        if not run(pending[start : start + batch_size]):
            break
    result.pending_left = pending_count(session, opportunity_id)
    if result.pending_left and result.outcome == "COMPLETED":
        result.outcome = "PARTIAL"
        result.errors.append(
            {
                "code": "BATCH_LIMIT",
                "detail": f"Quedan {result.pending_left} videos sin sugerencia.",
            }
        )
    return result


def accept_suggestions(
    session: Session,
    opportunity_id: str,
    *,
    min_confidence: str,
    reviewer: str,
    now: datetime,
) -> dict[str, Any]:
    """Acción humana: pasa a revisión las sugerencias con confianza suficiente."""
    if min_confidence not in ("HIGH", "MEDIUM"):
        raise ProblemError(422, "INVALID_CONFIDENCE", "La confianza mínima es HIGH o MEDIUM")
    matches = session.scalars(
        select(m.DiscoveryMatch).where(
            m.DiscoveryMatch.opportunity_id == opportunity_id,
            m.DiscoveryMatch.is_spanish_market.is_(True),
            m.DiscoveryMatch.match_quality == "UNREVIEWED",
            m.DiscoveryMatch.ai_quality.is_not(None),
        )
    ).all()
    accepted_videos: dict[str, str] = {}
    skipped_videos: set[str] = set()
    for match in matches:
        if cr.meets(match.ai_confidence, min_confidence) and match.ai_quality in cr.QUALITIES:
            match.match_quality = str(match.ai_quality)
            match.reviewed_by = f"{reviewer}{BULK_SUFFIX}"
            accepted_videos[match.video_id] = str(match.ai_quality)
        else:
            skipped_videos.add(match.video_id)
    skipped_videos -= set(accepted_videos)
    by_quality: dict[str, int] = {}
    for quality in accepted_videos.values():
        by_quality[quality] = by_quality.get(quality, 0) + 1
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=None,
            actor=reviewer,
            event_type="MATCHES_ACCEPTED_FROM_AI",
            object_type="opportunity",
            object_id=opportunity_id,
            details_redacted_json={
                "min_confidence": min_confidence,
                "accepted": len(accepted_videos),
                "by_quality": by_quality,
            },
        )
    )
    session.flush()
    if accepted_videos:
        spanish_service.record_assessment(session, opportunity_id, None, now)
    return {
        "accepted": len(accepted_videos),
        "by_quality": by_quality,
        "left_for_manual_review": len(skipped_videos),
        "min_confidence": min_confidence,
    }
