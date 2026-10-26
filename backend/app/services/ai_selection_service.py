"""Qué IA y qué modelo usa cada función (D-68).

Hay tres funciones: el asistente, la clasificación de competidores y el plan de búsqueda en
español. Cada una puede tener su propio modelo, elegido entre los del catálogo de
`config/research.yaml` y guardado en la base: el cambio rige sin reiniciar. Sin elección guardada
rige `AI_PROVIDER` y `AI_MODEL` del entorno, como antes. Un proveedor solo se puede elegir si su
clave está definida; las claves nunca salen de aquí.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.core.research_config import load_research_config
from app.db import models as m
from app.providers.ai import MAX_OUTPUT_TOKENS, AIClient, build_ai_client

PROVIDERS = ("anthropic", "openai")
FUNCTIONS: dict[str, dict[str, str]] = {
    "assistant": {
        "label": "Asistente",
        "description": "Responde preguntas sobre una oportunidad, en conversación.",
        "suggestion": "Un modelo de complejidad media suele bastar para interpretar métricas.",
    },
    "classification": {
        "label": "Clasificación de competidores",
        "description": "Sugiere la calidad de cada competidor en español, por lotes.",
        "suggestion": "Tarea masiva y repetitiva: conviene un modelo rápido y económico.",
    },
    "plan": {
        "label": "Plan de búsqueda en español",
        "description": "Propone las consultas en español de una oportunidad.",
        "suggestion": "Se usa poco y conviene que sea bueno: un modelo de complejidad media.",
    },
}
DEFAULT_SOURCE = "default"
USER_SOURCE = "user"


def catalog(settings: Settings) -> list[dict[str, str]]:
    """Modelos permitidos, tal como los define config/research.yaml."""
    raw = load_research_config(settings.research_config_path).get("ai", {}).get("models", [])
    return [
        {
            "provider": str(item["provider"]),
            "model": str(item["model"]),
            "label": str(item.get("label") or item["model"]),
            "description": str(item.get("description") or ""),
        }
        for item in raw
        if isinstance(item, dict) and item.get("provider") in PROVIDERS and item.get("model")
    ]


def provider_has_key(settings: Settings, provider: str) -> bool:
    keys = {
        "anthropic": settings.anthropic_api_key.get_secret_value(),
        "openai": settings.openai_api_key.get_secret_value(),
    }
    return bool(keys.get(provider))


def _require_function(function: str) -> None:
    if function not in FUNCTIONS:
        raise ProblemError(404, "AI_FUNCTION_NOT_FOUND", "Función de IA desconocida")


def selection(session: Session, settings: Settings, function: str) -> dict[str, Any]:
    """Proveedor y modelo vigentes de una función, y de dónde salen."""
    _require_function(function)
    row = session.get(m.AiSelection, function)
    if row is not None:
        provider, model, source = row.provider, row.model, USER_SOURCE
    else:
        provider, model, source = settings.ai_provider, settings.ai_model, DEFAULT_SOURCE
    return {
        "function": function,
        "provider": provider,
        "model": model or None,
        "source": source,
        "configured": provider in PROVIDERS
        and bool(model)
        and provider_has_key(settings, provider),
    }


def configured(session: Session, settings: Settings, function: str) -> bool:
    return bool(selection(session, settings, function)["configured"])


def build_client(
    session: Session,
    settings: Settings,
    function: str,
    *,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
) -> AIClient:
    chosen = selection(session, settings, function)
    return build_ai_client(
        settings,
        max_output_tokens=max_output_tokens,
        provider=str(chosen["provider"]),
        model=str(chosen["model"] or ""),
    )


def set_selection(
    session: Session,
    settings: Settings,
    function: str,
    *,
    provider: str,
    model: str,
    by: str,
) -> dict[str, Any]:
    _require_function(function)
    if not any(c["provider"] == provider and c["model"] == model for c in catalog(settings)):
        raise ProblemError(
            422,
            "AI_MODEL_NOT_ALLOWED",
            "Modelo no permitido",
            "Elija uno de la lista (se edita en config/research.yaml).",
        )
    if not provider_has_key(settings, provider):
        raise ProblemError(
            409,
            "AI_PROVIDER_NOT_CONFIGURED",
            "Falta la clave del proveedor",
            f"Defina la clave de {provider} en el entorno y reinicie la API y el worker.",
        )
    previous = selection(session, settings, function)
    row = session.get(m.AiSelection, function)
    if row is None:
        session.add(
            m.AiSelection(function_id=function, provider=provider, model=model, updated_by=by)
        )
    else:
        row.provider, row.model, row.updated_by = provider, model, by
    _audit(session, function, by, {"provider": provider, "model": model, "previous": previous})
    session.flush()
    return selection(session, settings, function)


def clear_selection(
    session: Session, settings: Settings, function: str, *, by: str
) -> dict[str, Any]:
    """Vuelve a lo que dice el entorno (AI_PROVIDER y AI_MODEL)."""
    _require_function(function)
    row = session.get(m.AiSelection, function)
    if row is not None:
        _audit(session, function, by, {"reset_to_default": True, "previous_model": row.model})
        session.delete(row)
        session.flush()
    return selection(session, settings, function)


def _audit(session: Session, function: str, by: str, details: dict[str, Any]) -> None:
    from uuid import uuid4

    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=None,
            actor=by,
            event_type="AI_SELECTION_CHANGED",
            object_type="ai_selection",
            object_id=function,
            details_redacted_json=details,
        )
    )


def overview(session: Session, settings: Settings) -> dict[str, Any]:
    return {
        "functions": [
            {"id": fid, **meta, **selection(session, settings, fid)}
            for fid, meta in FUNCTIONS.items()
        ],
        "catalog": [
            {**c, "available": provider_has_key(settings, c["provider"])} for c in catalog(settings)
        ],
        "default": {"provider": settings.ai_provider, "model": settings.ai_model or None},
    }
