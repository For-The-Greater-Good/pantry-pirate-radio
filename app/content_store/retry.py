"""Retry mechanisms for content store database operations."""

import functools
import sqlite3
import time
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_db_retry(
    max_retries: int = 5,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (sqlite3.OperationalError,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that adds retry logic with exponential backoff for database operations.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for exponential backoff
        retry_on: Tuple of exception types to retry on

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Check if this exception type should trigger a retry
                    should_retry = any(isinstance(e, exc_type) for exc_type in retry_on)

                    # Check for specific database lock messages
                    if isinstance(e, sqlite3.OperationalError):
                        error_msg = str(e).lower()
                        # Only skip retry for specific non-recoverable errors
                        if (
                            "database is locked" not in error_msg
                            and "database table is locked" not in error_msg
                            and "cannot start a transaction within a transaction"
                            not in error_msg
                        ):
                            # Check if this is a non-recoverable operational error
                            if (
                                "no such table" in error_msg
                                or "no such column" in error_msg
                                or "syntax error" in error_msg
                            ):
                                should_retry = False
                            # Otherwise, keep the original should_retry value for other operational errors

                    if not should_retry or attempt == max_retries:
                        # Don't retry on this exception type or max retries reached
                        raise e

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (backoff_factor**attempt), max_delay)

                    logger.debug(
                        f"Database operation failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    time.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


def with_transaction_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator specifically for SQLite transaction operations.

    Uses more aggressive retry settings for transaction-level operations
    that are more likely to encounter locks.
    """
    return with_db_retry(
        max_retries=8,
        base_delay=0.05,
        max_delay=1.0,
        backoff_factor=1.5,
        retry_on=(sqlite3.OperationalError, sqlite3.DatabaseError),
    )(func)


def with_connection_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator for SQLite connection operations.

    Uses moderate retry settings for connection-level operations.
    """
    return with_db_retry(
        max_retries=5,
        base_delay=0.1,
        max_delay=2.0,
        backoff_factor=2.0,
        retry_on=(sqlite3.OperationalError,),
    )(func)
