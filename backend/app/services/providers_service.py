from app.api.v1.schemas import ProviderOut
from app.core.config import Settings


def list_providers(settings: Settings) -> list[ProviderOut]:
    """Estado de adaptadores. Solo indica si hay credencial; nunca expone su valor."""
    youtube_configured = bool(settings.youtube_api_key.get_secret_value())
    vidiq_configured = bool(settings.vidiq_api_key.get_secret_value())
    hasdata_configured = bool(settings.hasdata_api_key.get_secret_value())
    llm_key = {
        "anthropic": settings.anthropic_api_key.get_secret_value(),
        "openai": settings.openai_api_key.get_secret_value(),
    }.get(settings.ai_provider, "")
    return [
        ProviderOut(
            id="synthetic_fixture",
            name="Dataset sintético DEMO",
            enabled=settings.demo_mode,
            status="SYNTHETIC" if settings.demo_mode else "DISABLED",
            license_note="Datos fabricados y rotulados. No son de YouTube.",
        ),
        ProviderOut(
            id="youtube_official",
            name="YouTube Data API (oficial)",
            enabled=True,
            status="CONFIGURED" if youtube_configured else "NOT_CONFIGURED",
            license_note="Metadatos públicos sujetos a las políticas de YouTube. Adaptador en M1.",
        ),
        ProviderOut(
            id="vidiq_import",
            name="Importación vidIQ (CSV/JSON exportado)",
            enabled=False,
            status="NOT_CONFIGURED",
            license_note="Requiere exportación con derechos de reutilización. Importador en M1.",
        ),
        ProviderOut(
            id="vidiq_api",
            name="vidIQ API directa",
            enabled=vidiq_configured,
            status="CONFIGURED" if vidiq_configured else "NOT_CONFIGURED",
            license_note=(
                "MCP de solo lectura con clave; consume créditos del plan. Sujeto a la "
                "compuerta de políticas (capacidad vidiq_api) y a la caducidad de 29 días."
            ),
        ),
        ProviderOut(
            id="google_trends",
            name="Google Trends vía HasData (índice relativo)",
            enabled=hasdata_configured,
            status="CONFIGURED" if hasdata_configured else "NOT_CONFIGURED",
            license_note=(
                "Índice relativo de 0 a 100, no volúmenes. HasData obtiene los datos por scraping "
                "de terceros: uso autorizado por el responsable (capacidad google_trends)."
            ),
        ),
        ProviderOut(
            id="llm_analysis",
            name=f"Análisis IA ({settings.ai_provider})",
            enabled=settings.ai_provider != "none",
            status="CONFIGURED"
            if llm_key
            else ("DISABLED" if settings.ai_provider == "none" else "NOT_CONFIGURED"),
            license_note="Salidas JSON validadas; cada hecho debe citar su source_id. Fase M2.",
        ),
    ]
