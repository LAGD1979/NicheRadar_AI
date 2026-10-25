"""Reglas puras de clasificación de videos y canales (spec §3.3). Sin I/O: fáciles de probar."""

import re
from dataclasses import dataclass

# Por debajo de este umbral un video no puede confirmarse como largo ni como Short.
SHORT_CHECK_THRESHOLD_SECONDS = 180

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_iso_duration(value: str | None) -> int | None:
    """Duración ISO 8601 de YouTube (p. ej. PT1H2M3S) a segundos. Vacía o inválida → None."""
    if not value:
        return None
    match = _DURATION.match(value)
    if match is None or value in ("P", "PT"):
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return days * 86_400 + hours * 3_600 + minutes * 60 + seconds


def primary_language(code: str | None) -> str | None:
    """Idioma base del código BCP-47. Preserva las variantes de chino (zh-Hans, zh-Hant)."""
    if not code:
        return None
    normalized = code.strip()
    if normalized.lower().startswith("zh-hans") or normalized.lower().startswith("zh-hant"):
        return "zh-Hans" if "hans" in normalized.lower() else "zh-Hant"
    return normalized.split("-")[0].lower() or None


@dataclass(frozen=True)
class LanguageVerdict:
    state: str
    confidence: str


def classify_language(default_audio: str | None, default_metadata: str | None) -> LanguageVerdict:
    """Precedencia de spec §3.3: audio declarado > metadatos. Un conflicto nunca se fuerza (T04)."""
    audio = primary_language(default_audio)
    meta = primary_language(default_metadata)
    if audio and meta:
        if audio == meta:
            return LanguageVerdict(audio, "HIGH")
        return LanguageVerdict("UNKNOWN", "CONFLICT")
    if audio:
        return LanguageVerdict(audio, "HIGH")
    if meta:
        return LanguageVerdict(meta, "MEDIUM")
    return LanguageVerdict("UNKNOWN", "NONE")


@dataclass(frozen=True)
class TypeVerdict:
    video_type: str
    evidence: str


def classify_video_type(duration_seconds: int | None, live_broadcast: str | None) -> TypeVerdict:
    """LONG/SHORT no se mezclan (spec §0.5). La duración sola no prueba que sea Short."""
    if live_broadcast in ("live", "upcoming"):
        return TypeVerdict("LIVE", f"liveBroadcastContent={live_broadcast}")
    if duration_seconds is None:
        return TypeVerdict("UNKNOWN", "duración ausente")
    if duration_seconds > SHORT_CHECK_THRESHOLD_SECONDS:
        return TypeVerdict(
            "LONG", f"duración {duration_seconds} s > {SHORT_CHECK_THRESHOLD_SECONDS} s"
        )
    return TypeVerdict(
        "UNKNOWN", f"duración {duration_seconds} s; sin confirmación de clasificación Short"
    )


def parse_count(raw: str | int | None) -> int | None:
    """Contador público. Ausente o no numérico → None (nunca 0). Un cero real se conserva."""
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None
