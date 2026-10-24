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
    demo_mode: bool = True

    youtube_search_daily_soft_limit: int = 80
    youtube_other_daily_soft_limit: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
