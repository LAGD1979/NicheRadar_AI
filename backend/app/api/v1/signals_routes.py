"""Demanda en español y persistencia temporal con fuentes externas (D-63).

Las mediciones gastan créditos de proveedores externos, así que corren como corridas del worker.
Cada una exige la clave del proveedor (409) y la compuerta de políticas de su capacidad (403).
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ProblemError
from app.db import models as m
from app.db.session import get_session
from app.services import demand_service, demand_state
from app.services.compliance_service import decide
from app.services.research_service import enqueue_run

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

HASDATA_CREDITS_PER_CALL = 10  # documentación de HasData: 10 créditos por consulta


Source = Literal["trends", "vidiq"]


def _all_sources() -> list[Source]:
    return ["trends", "vidiq"]


class DemandRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=demand_service.MAX_KEYWORDS)
    geo: str | None = Field(default=None, pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")
    sources: list[Source] = Field(default_factory=_all_sources, min_length=1, max_length=2)
    include_related: bool = False
    force: bool = False  # repetir aunque haya una medición reciente con los mismos términos

    @field_validator("keywords")
    @classmethod
    def _clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            text = raw.strip()
            if not 2 <= len(text) <= 80:
                raise ValueError("cada palabra clave debe tener entre 2 y 80 caracteres")
            if any(ord(ch) < 32 for ch in text):
                raise ValueError("contiene caracteres de control")
            if "," in text:
                raise ValueError("no puede contener comas (la coma separa los términos)")
            if text.lower() not in {c.lower() for c in cleaned}:
                cleaned.append(text)
        return cleaned

    @field_validator("sources")
    @classmethod
    def _unique_sources(cls, value: list[Source]) -> list[Source]:
        return list(dict.fromkeys(value))


class HistoryRequest(BaseModel):
    max_calls: int = Field(default=6, ge=1, le=10)


def _require(settings: Settings, session: Session, *, key: str, capability: str, name: str) -> None:
    if not key:
        raise ProblemError(
            409,
            "PROVIDER_NOT_CONFIGURED",
            f"{name} no está configurado",
            f"Defina la clave de {name} y reinicie la API y el worker.",
        )
    decision = decide(capability, settings, session)
    if not decision.allowed:
        raise ProblemError(403, "POLICY_RESTRICTED", f"{name} está restringido", decision.reason)


def _opportunity(session: Session, opportunity_id: str) -> m.Opportunity:
    opportunity = session.get(m.Opportunity, opportunity_id)
    if opportunity is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    return opportunity


@router.post("/opportunities/{opportunity_id}/demand", status_code=202)
def request_demand(
    opportunity_id: str, body: DemandRequest, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Encola la medición de demanda: Trends (HasData) y palabras clave (vidIQ)."""
    _opportunity(session, opportunity_id)
    if "trends" in body.sources:
        _require(
            settings,
            session,
            key=settings.hasdata_api_key.get_secret_value(),
            capability="google_trends",
            name="HasData",
        )
    if "vidiq" in body.sources:
        _require(
            settings,
            session,
            key=settings.vidiq_api_key.get_secret_value(),
            capability="vidiq_api",
            name="vidIQ",
        )
    # Los términos van juntos en una sola llamada; las relacionadas cuestan una por término.
    hasdata_calls = (
        (1 + (len(body.keywords) if body.include_related else 0)) if "trends" in body.sources else 0
    )
    vidiq_calls = len(body.keywords) if "vidiq" in body.sources else 0
    run = enqueue_run(
        session,
        kind="demand",
        policy_mode=settings.compliance_mode,
        payload={
            "opportunity_id": opportunity_id,
            "keywords": body.keywords,
            "geo": body.geo,
            "sources": body.sources,
            "include_related": body.include_related,
            "force": body.force,
        },
        params={"opportunity_id": opportunity_id, "keywords": len(body.keywords), "geo": body.geo},
        algorithm_version="demand-v1",
        budget={
            "hasdata_calls_estimate": hasdata_calls,
            "hasdata_credits_estimate": hasdata_calls * HASDATA_CREDITS_PER_CALL,
            "vidiq_credits_estimate": vidiq_calls * settings.vidiq_credits_per_call,
        },
    )
    session.commit()
    return {"id": run.id, "kind": run.kind, "status": run.status, "budget": run.budget_json}


@router.get("/opportunities/{opportunity_id}/demand")
def get_demand(opportunity_id: str, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    _opportunity(session, opportunity_id)
    return demand_state.summary(session, settings, opportunity_id, datetime.now(UTC))


@router.post("/opportunities/{opportunity_id}/temporal-resilience", status_code=202)
def request_temporal_resilience(
    opportunity_id: str, body: HistoryRequest, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Encola la medición de persistencia de los videos agrupados (vidIQ, 5 créditos por video)."""
    _opportunity(session, opportunity_id)
    _require(
        settings,
        session,
        key=settings.vidiq_api_key.get_secret_value(),
        capability="vidiq_api",
        name="vidIQ",
    )
    run = enqueue_run(
        session,
        kind="history",
        policy_mode=settings.compliance_mode,
        payload={"opportunity_id": opportunity_id, "max_calls": body.max_calls},
        params={"opportunity_id": opportunity_id, "max_calls": body.max_calls},
        algorithm_version="persist-v1",
        budget={"vidiq_credits_estimate": body.max_calls * settings.vidiq_credits_per_call},
    )
    session.commit()
    return {"id": run.id, "kind": run.kind, "status": run.status, "budget": run.budget_json}


@router.get("/usage/hasdata")
def usage_hasdata(session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    return demand_service.hasdata_snapshot(session, settings, datetime.now(UTC))
