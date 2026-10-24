from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@lru_cache
def load_research_config(path: str) -> dict[str, Any]:
    """Carga config/research.yaml. Son valores editables, no límites reales del proveedor."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "research" not in data or "quota" not in data:
        raise RuntimeError(f"Configuración de investigación inválida: {path}")
    return data
