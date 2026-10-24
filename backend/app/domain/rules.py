from datetime import datetime


def age_hours(published_at: datetime, observed_at: datetime) -> float:
    """Edad del video en horas, con mínimo de 1 h para evitar 0 y divisiones por cero (T03).

    Una fecha de publicación posterior a la observación es un dato inconsistente y se rechaza.
    """
    if published_at.tzinfo is None or observed_at.tzinfo is None:
        raise ValueError("Las fechas deben incluir zona horaria (UTC).")
    delta_seconds = (observed_at - published_at).total_seconds()
    if delta_seconds < 0:
        raise ValueError("observed_at es anterior a published_at.")
    return max(1.0, delta_seconds / 3600)


def subscriber_band(subscriber_count: int | None) -> str:
    """Bandas de suscriptores de spec §3.3. NULL es UNKNOWN, no cero (T02)."""
    if subscriber_count is None:
        return "UNKNOWN"
    if subscriber_count < 1_000:
        return "[0,1000)"
    if subscriber_count < 10_000:
        return "[1000,10000)"
    if subscriber_count < 50_000:
        return "[10000,50000)"
    if subscriber_count < 100_000:
        return "[50000,100000)"
    return ">=100000"
