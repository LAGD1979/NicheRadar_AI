from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración validada desde el entorno. Los secretos son SecretStr y no se imprimen."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    # Sin "production" en M0: no hay autenticación implementada (spec §15.1).
    app_env: Literal["development", "test"] = "development"
    app_base_url: str = "http://localhost:5173"
    database_url: str = "postgresql+psycopg://nicheradar:nicheradar@db:5432/nicheradar"
    research_config_path: str = "../config/research.yaml"
    log_level: str = "INFO"

    youtube_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    app_secret_key: SecretStr = SecretStr("")

    # Solo "restricted" existe en M0. Otros modos llegarán con policy_approvals (M4).
    compliance_mode: Literal["restricted"] = "restricted"
    advanced_analytics_enabled: bool = False
    ai_provider: Literal["none", "anthropic", "openai"] = "none"
    # Modelo configurable por entorno; vacío = no hay modelo y la IA no se ejecuta (spec §17).
    ai_model: str = ""
    ai_max_usd_per_run: float = 5.0
    demo_mode: bool = True

    # Cuota de YouTube Data API: pool diario compartido en unidades (search.list = 100 u.).
    # El día de cuota es el de Pacific Time; ver docs/DECISIONS.md (D-22).
    youtube_api_base_url: str = "https://www.googleapis.com/youtube/v3"
    youtube_timeout_seconds: float = 15.0
    youtube_max_retries: int = 3
    youtube_daily_units_limit: int = 10_000
    youtube_daily_units_soft_pct: float = 0.9
    # Datos de terceros no autorizados: plazo máximo de caché (spec §5.5, 30 días menos margen).
    unauthorized_cache_days: int = 29


@lru_cache
def get_settings() -> Settings:
    return Settings()
