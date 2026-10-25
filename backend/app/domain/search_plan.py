"""Esquema del plan de búsqueda en español (spec §3.5, §6.2), validado antes de guardarse."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_URL = re.compile(r"(https?://|www\.|\.com\b|\.org\b|\.net\b)", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_QUERIES_PER_GROUP = 10
MIN_GLOBAL_QUERIES = 5


def _clean_text(value: str, *, max_len: int) -> str:
    if _CONTROL.search(value):
        raise ValueError("contiene caracteres de control")
    if _URL.search(value):
        raise ValueError("contiene una URL: las búsquedas no deben incluir enlaces")
    if len(value) > max_len:
        raise ValueError(f"supera {max_len} caracteres")
    return value.strip()


class QueryGroup(BaseModel):
    region: Literal["ALL_ES", "LATAM", "ES"]
    language: Literal["es"] = "es"
    queries: list[str] = Field(min_length=1, max_length=MAX_QUERIES_PER_GROUP)
    exclusions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("queries")
    @classmethod
    def _queries_are_text(cls, values: list[str]) -> list[str]:
        cleaned = [_clean_text(v, max_len=120) for v in values]
        if any(len(v) < 2 for v in cleaned):
            raise ValueError("cada búsqueda necesita al menos 2 caracteres")
        return cleaned

    @field_validator("exclusions")
    @classmethod
    def _exclusions_are_text(cls, values: list[str]) -> list[str]:
        return [_clean_text(v, max_len=60) for v in values]


class SpanishSearchPlan(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    canonical_concept_es: str = Field(min_length=3, max_length=200)
    same_format_definition: str = Field(min_length=10, max_length=600)
    query_groups: list[QueryGroup] = Field(min_length=1, max_length=3)
    adjacent_but_distinct: list[str] = Field(default_factory=list, max_length=10)
    localization_notes: list[str] = Field(default_factory=list, max_length=10)
    source_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("canonical_concept_es", "same_format_definition")
    @classmethod
    def _text_fields(cls, value: str) -> str:
        return _clean_text(value, max_len=600)

    @field_validator("adjacent_but_distinct", "localization_notes")
    @classmethod
    def _notes(cls, values: list[str]) -> list[str]:
        return [_clean_text(v, max_len=200) for v in values]

    @model_validator(mode="after")
    def _shape(self) -> "SpanishSearchPlan":
        regions = [g.region for g in self.query_groups]
        if len(set(regions)) != len(regions):
            raise ValueError("cada región aparece una sola vez")
        global_group = next((g for g in self.query_groups if g.region == "ALL_ES"), None)
        if global_group is None or len(global_group.queries) < MIN_GLOBAL_QUERIES:
            raise ValueError(f"el grupo ALL_ES necesita al menos {MIN_GLOBAL_QUERIES} búsquedas")
        return self


def query_texts(plan: SpanishSearchPlan) -> list[tuple[str, str]]:
    """(región, búsqueda) de todos los grupos, en orden, sin duplicados."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for group in plan.query_groups:
        for query in group.queries:
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((group.region, query))
    return out
