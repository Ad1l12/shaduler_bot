"""structlog configuration — JSON output to stdout.

Call ``configure_logging()`` once at application startup (inside the FastAPI
lifespan, before any log statements are made).

Secret filtering
----------------
``_filter_secrets`` removes well-known sensitive key names from every log
record before it is serialised.  This ensures tokens, passwords, and keys are
never written to stdout even if a developer accidentally logs them.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from src.config import settings

# Keys whose values should never appear in logs.
_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "encrypted_access_token",
        "encrypted_refresh_token",
        "password",
        "secret",
        "encryption_key",
        "client_secret",
        "api_key",
    }
)


def _filter_secrets(
    _logger: WrappedLogger,
    _method: str,
    event_dict: EventDict,
) -> EventDict:
    """Replace secret values with ``"[REDACTED]"`` in every log record."""
    for key in list(event_dict.keys()):
        if key in _SECRET_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging() -> None:
    """Set up structlog with JSON rendering and Python stdlib integration."""
    log_level: int = getattr(logging, settings.app_log_level.value, logging.INFO)

    # Configure the stdlib root logger so that libraries that use logging
    # (SQLAlchemy, APScheduler, httpx, …) are also captured by structlog.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _filter_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Redirect stdlib loggers to structlog so library output is uniform.
    structlog.stdlib.recreate_defaults(log_level=log_level)
