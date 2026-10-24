import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

SECRET_KEY_PATTERN = re.compile(r"(key|secret|token|password)", re.IGNORECASE)


def redact_secrets(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for name in list(event_dict):
        if SECRET_KEY_PATTERN.search(name):
            event_dict[name] = "***REDACTED***"
    return event_dict


def configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )
