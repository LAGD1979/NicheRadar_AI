"""Asistente de IA por oportunidad (D-67): solo lectura, con contexto agregado y citas.

La IA no ejecuta nada ni cambia datos: responde preguntas sobre el resumen de la oportunidad y
sugiere pasos. Lo que devuelve se valida: las citas deben ser secciones reales del contexto y una
respuesta con cifras pero sin citas se marca para que la persona la verifique.
"""

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.db import models as m
from app.prompts import assistant_v1
from app.providers.ai import AIClient
from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderUnavailable,
    QuotaExhausted,
)
from app.services import assistant_context, vidiq_service
from app.services.spanish_service import _strip_fences

PROVIDER = "ai_assistant"
BUCKET = "assistant_messages"
MAX_QUESTION_CHARS = 1000
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 700
MAX_ANSWER_CHARS = 4000
MAX_LIST_ITEMS = 3
CHARS_PER_TOKEN = 4
ROLES = ("user", "assistant")


def tokens_estimate(text: str) -> int:
    """Estimación gruesa (4 caracteres por token); sirve para mostrar el costo, no para facturar."""
    return -(-len(text) // CHARS_PER_TOKEN)


def messages_today(session: Session, now: datetime) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(m.ProviderUsage.units), 0)).where(
            m.ProviderUsage.provider == PROVIDER,
            m.ProviderUsage.quota_bucket == BUCKET,
            m.ProviderUsage.started_at >= vidiq_service.day_start(now),
        )
    )
    return int(total or 0)


def status(
    session: Session, settings: Settings, now: datetime, *, selection: dict[str, Any]
) -> dict[str, Any]:
    used = messages_today(session, now)
    return {
        "configured": selection["configured"],
        "provider": selection["provider"],
        "model": selection["model"],
        "model_source": selection["source"],
        "messages_used_today": used,
        "messages_daily_limit": settings.assistant_daily_message_limit,
        "messages_remaining": max(0, settings.assistant_daily_message_limit - used),
        "prompt_version": assistant_v1.PROMPT_VERSION,
    }


def clean_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Últimos turnos, recortados: el historial es dato no confiable y cuesta tokens."""
    turns = [
        {"role": t["role"], "content": t["content"].strip()[:MAX_HISTORY_CHARS]}
        for t in history
        if t.get("role") in ROLES and t.get("content", "").strip()
    ]
    return turns[-MAX_HISTORY_TURNS:]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:400] for v in value if isinstance(v, str) and v.strip()][
        :MAX_LIST_ITEMS
    ]


def parse_answer(text: str) -> dict[str, Any]:
    """Respuesta estructurada de la IA; si no es JSON válido, se conserva el texto sin citas."""
    try:
        data = json.loads(_strip_fences(text))
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
        return {
            "answer": text.strip()[:MAX_ANSWER_CHARS],
            "citations": [],
            "unknowns": [],
            "next_steps": [],
            "structured": False,
        }
    citations = [
        c
        for c in dict.fromkeys(data.get("citations") or [])
        if isinstance(c, str) and c in assistant_context.SECTIONS
    ]
    return {
        "answer": data["answer"].strip()[:MAX_ANSWER_CHARS],
        "citations": citations,
        "unknowns": _strings(data.get("unknowns")),
        "next_steps": _strings(data.get("next_steps")),
        "structured": True,
    }


def ask(
    session: Session,
    settings: Settings,
    client: AIClient,
    *,
    opportunity_id: str,
    question: str,
    history: list[dict[str, str]],
    now: datetime,
) -> dict[str, Any]:
    question = question.strip()
    if not question or len(question) > MAX_QUESTION_CHARS:
        raise ProblemError(
            422,
            "INVALID_QUESTION",
            "Pregunta no válida",
            f"Escriba una pregunta de hasta {MAX_QUESTION_CHARS} caracteres.",
        )
    used = messages_today(session, now)
    if used + 1 > settings.assistant_daily_message_limit:
        raise ProblemError(
            429,
            "ASSISTANT_LIMIT",
            "Tope diario del asistente",
            f"Se alcanzaron {used} de {settings.assistant_daily_message_limit} mensajes de hoy.",
        )
    context = assistant_context.build(session, settings, opportunity_id)
    user_message = assistant_v1.build_user_message(context, clean_history(history), question)
    session.add(
        m.ProviderUsage(
            id=str(uuid4()),
            run_id=None,
            provider=PROVIDER,
            endpoint=client.model or "assistant",
            quota_bucket=BUCKET,
            units=1,
            started_at=now,
            status="RESERVED",
        )
    )
    session.commit()  # se cuenta aunque la llamada falle: puede haber gastado tokens
    try:
        text = client.complete(assistant_v1.SYSTEM, user_message)
    except ProviderAuthError as exc:
        raise ProblemError(502, "AI_AUTH_ERROR", "La IA rechazó la clave", str(exc)) from exc
    except (QuotaExhausted, ProviderUnavailable) as exc:
        raise ProblemError(503, "AI_UNAVAILABLE", "La IA no está disponible", str(exc)) from exc
    except InvalidRequest as exc:
        raise ProblemError(502, "AI_BAD_RESPONSE", "La IA no pudo responder", str(exc)) from exc
    parsed = parse_answer(text)
    parsed["unsourced"] = bool(re.search(r"\d", parsed["answer"])) and not parsed["citations"]
    parsed.update(
        model=client.model,
        prompt_version=assistant_v1.PROMPT_VERSION,
        context_tokens_estimate=tokens_estimate(user_message)
        + tokens_estimate(assistant_v1.SYSTEM),
        answer_tokens_estimate=tokens_estimate(text),
        messages_remaining=max(0, settings.assistant_daily_message_limit - used - 1),
        generated_at=now.isoformat(),
    )
    return parsed
