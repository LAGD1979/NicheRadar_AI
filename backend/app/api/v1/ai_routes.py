"""Elección de IA y modelo por función (D-68). No expone claves."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services import ai_selection_service

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class SelectionBody(BaseModel):
    provider: Literal["anthropic", "openai"]
    model: str = Field(min_length=1, max_length=80)


@router.get("/ai/settings")
def get_ai_settings(session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    return ai_selection_service.overview(session, settings)


@router.put("/ai/settings/{function}")
def put_ai_setting(
    function: str, body: SelectionBody, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    chosen = ai_selection_service.set_selection(
        session, settings, function, provider=body.provider, model=body.model, by="local_owner"
    )
    session.commit()
    return chosen


@router.delete("/ai/settings/{function}")
def delete_ai_setting(function: str, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    chosen = ai_selection_service.clear_selection(session, settings, function, by="local_owner")
    session.commit()
    return chosen
