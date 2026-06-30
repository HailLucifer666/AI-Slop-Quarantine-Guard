"""Structured logging with structlog and correlation-id tracking.

Minimal real implementation for JSON logging + correlation ID.
"""

import structlog
import uuid
from contextvars import ContextVar


# Correlation ID context variable
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def setup_logging():
    """Configure structlog for JSON output with correlation ID."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.CallsiteParameterAdder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structlog logger with correlation ID."""
    correlation_id = correlation_id_var.get()
    return structlog.get_logger(name).bind(
        correlation_id=correlation_id or str(uuid.uuid4())
    )


def set_correlation_id(correlation_id: Optional[str] = None):
    """Set or generate a correlation ID for the current context."""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    correlation_id_var.set(correlation_id)
