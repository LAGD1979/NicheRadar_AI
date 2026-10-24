import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import redact_secrets
from app.services.compliance_service import decide


def test_restricted_blocks_advanced_scores_by_default() -> None:
    decision = decide("advanced_scores", Settings())
    assert decision.allowed is False
    assert decision.state == "RESTRICTED"


def test_env_flag_alone_does_not_unlock_restricted_capability() -> None:
    # T17: ADVANCED_ANALYTICS_ENABLED=true por sí solo no basta.
    settings = Settings(advanced_analytics_enabled=True)
    decision = decide("advanced_scores", settings)
    assert decision.allowed is False


def test_unknown_capability_is_rejected() -> None:
    with pytest.raises(KeyError):
        decide("inventada", Settings())


def test_only_restricted_compliance_mode_is_accepted() -> None:
    with pytest.raises(ValidationError):
        Settings(compliance_mode="open")  # type: ignore[arg-type]


def test_production_environment_is_rejected_in_m0() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")  # type: ignore[arg-type]


def test_log_redaction_hides_secret_like_keys() -> None:
    event = {"event": "x", "youtube_api_key": "AIza-real", "password": "p", "count": 3}
    redacted = redact_secrets(None, "info", dict(event))
    assert redacted["youtube_api_key"] == "***REDACTED***"
    assert redacted["password"] == "***REDACTED***"
    assert redacted["count"] == 3
