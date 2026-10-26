"""Asistente de IA por oportunidad (D-67). Solo lectura: no cambia datos ni dispara corridas."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ProblemError
from app.db import models as m
from app.db.session import get_session
from app.providers.ai import AIClient
from app.providers.base import ProviderNotConfigured
from app.services import ai_selection_service, assistant_context, assistant_service

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def ai_client(session: SessionDep, settings: SettingsDep) -> Iterator[AIClient]:
    """Cliente de IA del asistente (el modelo elegido para esa función); las pruebas lo simulan."""
    if not ai_selection_service.configured(session, settings, "assistant"):
        raise ProblemError(
            409,
            "AI_NOT_CONFIGURED",
            "La IA no está configurada",
            "Defina AI_PROVIDER, la clave del proveedor y AI_MODEL, y reinicie la API.",
        )
    try:
        client = ai_selection_service.build_client(
            session,
            settings,
            "assistant",
            max_output_tokens=settings.assistant_max_output_tokens,
        )
    except ProviderNotConfigured as exc:
        raise ProblemError(409, "AI_NOT_CONFIGURED", "La IA no está configurada", str(exc)) from exc
    try:
        yield client
    finally:
        client.close()


AIDep = Annotated[AIClient, Depends(ai_client)]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=assistant_service.MAX_QUESTION_CHARS)
    history: list[Turn] = Field(default_factory=list, max_length=40)


def _opportunity(session: Session, opportunity_id: str) -> None:
    if session.get(m.Opportunity, opportunity_id) is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")


@router.get("/assistant/status")
def assistant_status(session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    return assistant_service.status(
        session,
        settings,
        datetime.now(UTC),
        selection=ai_selection_service.selection(session, settings, "assistant"),
    )


@router.get("/opportunities/{opportunity_id}/assistant/context")
def assistant_context_view(
    opportunity_id: str, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Exactamente lo que recibe la IA sobre la oportunidad, para que la persona lo vea."""
    _opportunity(session, opportunity_id)
    context = assistant_context.build(session, settings, opportunity_id)
    return {
        "context": context,
        "sections": list(assistant_context.SECTIONS),
        "tokens_estimate": assistant_service.tokens_estimate(
            json.dumps(context, ensure_ascii=False)
        ),
    }


@router.post("/opportunities/{opportunity_id}/assistant")
def assistant_ask(
    opportunity_id: str,
    body: AskRequest,
    session: SessionDep,
    settings: SettingsDep,
    client: AIDep,
) -> dict[str, Any]:
    _opportunity(session, opportunity_id)
    return assistant_service.ask(
        session,
        settings,
        client,
        opportunity_id=opportunity_id,
        question=body.message,
        history=[t.model_dump() for t in body.history],
        now=datetime.now(UTC),
    )
