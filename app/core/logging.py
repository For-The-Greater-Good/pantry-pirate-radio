"""Logging configuration module."""

from logging import (
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    Handler,
    Logger,
    StreamHandler,
    getLogger,
)
from typing import Any, TypeVar, cast

import structlog
from structlog import dev, processors, stdlib
from structlog.processors import JSONRenderer, TimeStamper, dict_tracebacks
from structlog.stdlib import BoundLogger
from structlog.types import EventDict, Processor, WrappedLogger

T = TypeVar("T", bound=Handler)

# Define log levels
LOG_LEVELS: dict[str, int] = {
    "debug": DEBUG,
    "info": INFO,
    "warning": WARNING,
    "error": ERROR,
    "critical": CRITICAL,
}


def configure_logging(testing: bool = False) -> None:
    """Configure structured logging for the application.

    Args:
        testing: Whether the application is running in test mode
    """
    # Configure root logger
    root_logger: Logger = getLogger()
    root_logger.setLevel(INFO)

    # Create and configure app logger
    app_logger: Logger = getLogger("app")
    app_logger.setLevel(INFO)

    # Create handler
    handler: Handler = StreamHandler()
    handler.setLevel(INFO)

    # Define shared processors
    shared_processors = [
        stdlib.add_logger_name,
        stdlib.add_log_level,
        stdlib.PositionalArgumentsFormatter(),
        TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
        dict_tracebacks,
    ]

    # Configure structlog
    structlog.configure(
        processors=[
            stdlib.filter_by_level,
            *shared_processors,
            processors.format_exc_info,
            JSONRenderer() if not testing else processors.KeyValueRenderer(),
        ],
        context_class=dict,
        logger_factory=stdlib.LoggerFactory(),
        wrapper_class=stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure handler formatter
    formatter = stdlib.ProcessorFormatter(
        processor=processors.JSONRenderer() if not testing else dev.ConsoleRenderer(),
        foreign_pre_chain=shared_processors,
    )
    handler.setFormatter(formatter)

    # Clear existing handlers to prevent duplicates
    root_logger.handlers = []
    app_logger.handlers = []

    root_logger.addHandler(handler)
    app_logger.addHandler(handler)


def get_logger() -> BoundLogger:
    """Get a configured logger instance.

    Returns:
        A structured logger instance.
    """
    return cast(BoundLogger, structlog.get_logger())


def get_request_logger(request_id: str | None = None) -> BoundLogger:
    """Get a logger with request context.

    Args:
        request_id: Optional request ID to bind to logger

    Returns:
        Configured logger with request context
    """
    logger: BoundLogger = get_logger()
    if request_id:
        logger = logger.bind(request_id=request_id)
    return logger


def add_request_metadata() -> Processor:
    """Create processor that adds request metadata to log entries.

    Returns:
        Processor that adds request context
    """

    def processor(
        logger: WrappedLogger,
        method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        # Add standard fields
        event_dict.update(
            {
                "logger_name": getattr(cast(Any, logger), "name", None),
                "log_level": method_name,
            }
        )
        return event_dict

    return processor
