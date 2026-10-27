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
    vidiq_api_key: SecretStr = SecretStr("")
    hasdata_api_key: SecretStr = SecretStr("")
    app_secret_key: SecretStr = SecretStr("")

    # "restricted" por defecto. "approved_scope" solo abre capacidades con un registro vigente
    # en policy_approvals (M4). Cambiar la variable sin registro no habilita nada.
    compliance_mode: Literal["restricted", "approved_scope"] = "restricted"
    advanced_analytics_enabled: bool = False
    ai_provider: Literal["none", "anthropic", "openai"] = "none"
    # Modelo configurable por entorno; vacío = no hay modelo y la IA no se ejecuta (spec §17).
    ai_model: str = ""
    ai_max_usd_per_run: float = 5.0
    # Asistente de IA por oportunidad (D-67): solo lectura, con contexto agregado.
    assistant_daily_message_limit: int = 100
    # Topes de tokens de IA (D-70): no hay precios en el repositorio, así que el límite es en
    # tokens reales informados por el proveedor, no en USD. El diario suma todas las funciones.
    ai_daily_token_limit: int = 1_000_000
    ai_run_token_limit: int = 300_000
    assistant_max_output_tokens: int = 4000
    # Backups locales de la base (M5, D-71): carpeta y días que se conservan. Un backup caduca
    # antes si contiene datos de terceros que vencen (29 días).
    backup_dir: str = "/backups"
    backup_retention_days: int = 14
    demo_mode: bool = True

    # Cuota de YouTube Data API: pool diario compartido en unidades (search.list = 100 u.).
    # El día de cuota es el de Pacific Time; ver docs/DECISIONS.md (D-22).
    youtube_api_base_url: str = "https://www.googleapis.com/youtube/v3"
    youtube_timeout_seconds: float = 15.0
    youtube_max_retries: int = 3
    youtube_daily_units_limit: int = 10_000
    youtube_daily_units_soft_pct: float = 0.9
    # vidIQ por MCP (D-57). Cada llamada de investigación cuesta créditos del plan del usuario;
    # el tope diario es local y conservador, no el saldo real del plan.
    vidiq_mcp_url: str = "https://mcp.vidiq.com/mcp"
    vidiq_timeout_seconds: float = 30.0
    vidiq_max_retries: int = 3
    vidiq_credits_per_call: int = 5
    vidiq_daily_credit_limit: int = 200
    # HasData (Google Trends por API REST, D-63). Cada consulta cuesta 10 créditos de HasData; los
    # topes son locales y cuentan consultas, no el saldo real del plan. El plan gratuito da 1.000
    # créditos al mes (100 consultas); el tope mensual deja un margen de 10 consultas.
    hasdata_base_url: str = "https://api.hasdata.com"
    hasdata_timeout_seconds: float = 45.0
    hasdata_max_retries: int = 3
    hasdata_daily_call_limit: int = 90
    hasdata_monthly_call_limit: int = 90
    # Una medición de Trends más reciente que esto, con los mismos términos, no se repite.
    hasdata_reuse_days: int = 7
    # Datos de terceros no autorizados: plazo máximo de caché (spec §5.5, 30 días menos margen).
    unauthorized_cache_days: int = 29


@lru_cache
def get_settings() -> Settings:
    return Settings()
