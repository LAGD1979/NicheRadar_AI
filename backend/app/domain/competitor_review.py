"""Sugerencias de la IA para clasificar competidores (spec §3.6 y §11). Funciones puras.

La IA solo **propone**: su salida se valida con un esquema estricto y nunca fija la calidad de una
coincidencia. Una persona la acepta o la corrige; solo entonces cuenta como revisión.

Reglas de la salida:
- JSON válido con el esquema de abajo; si no, se descarta el lote entero.
- Cada `source_id` debe estar en lo que se envió; un ID inventado descarta el lote (T13).
- Los motivos no pueden llevar enlaces.
- Lo que la IA no devuelva sigue pendiente: no se completa por defecto.
"""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

QUALITIES = ("EXACT", "ADJACENT", "GENERIC", "FALSE_POSITIVE")
CONFIDENCE_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
MAX_REASON = 200
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)


class Suggestion(BaseModel):
    source_id: str = Field(pattern=r"^V:[A-Za-z0-9_-]{6,20}$")
    quality: Literal["EXACT", "ADJACENT", "GENERIC", "FALSE_POSITIVE"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    reason: str = Field(min_length=5, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _no_links(cls, value: str) -> str:
        if _URL.search(value):
            raise ValueError("el motivo no puede incluir enlaces")
        return value.strip()


class ReviewResponse(BaseModel):
    schema_version: Literal["1.0"]
    classifications: list[Suggestion] = Field(max_length=100)


def strip_fences(raw: str) -> str:
    return _FENCE.sub("", raw.strip()).strip()


def parse(raw: str, allowed_ids: set[str]) -> tuple[list[Suggestion], str | None]:
    """Devuelve las sugerencias válidas y un código de error (None si todo está bien)."""
    try:
        data = json.loads(strip_fences(raw))
    except json.JSONDecodeError:
        return [], "INVALID_JSON"
    try:
        response = ReviewResponse.model_validate(data)
    except ValidationError:
        return [], "INVALID_SCHEMA"
    if any(item.source_id not in allowed_ids for item in response.classifications):
        return [], "INVALID_EVIDENCE_REF"
    seen: set[str] = set()
    unique: list[Suggestion] = []
    for item in response.classifications:
        if item.source_id not in seen:
            seen.add(item.source_id)
            unique.append(item)
    return unique, None


def meets(confidence: str | None, minimum: str) -> bool:
    return CONFIDENCE_RANK.get(confidence or "", 0) >= CONFIDENCE_RANK.get(minimum, 4)
