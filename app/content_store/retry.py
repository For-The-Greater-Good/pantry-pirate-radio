"""Retry mechanisms for content store database and AWS operations."""

import functools
import sqlite3
import time
import structlog
from typing import Any, Callable, TypeVar

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# AWS exception types that should trigger retries (transient errors)
AWS_RETRYABLE_ERROR_CODES = frozenset(
    {
        "Throttling",
        "ThrottlingException",
        "ProvisionedThroughputExceededException",
        "RequestLimitExceeded",
        "ServiceUnavailable",
        "InternalError",
        "InternalServerError",
        "RequestTimeout",
        "RequestTimeoutException",
        "TransactionConflictException",
        "ItemCollectionSizeLimitExceededException",
    }
)


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

                    # Check for AWS ClientError and determine if it's retryable
                    if _is_aws_client_error(e):
                        error_code = _get_aws_error_code(e)
                        if error_code in AWS_RETRYABLE_ERROR_CODES:
                            should_retry = True
                        else:
                            # Non-retryable AWS errors (AccessDenied, ValidationException, etc.)
                            should_retry = False

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


def _is_aws_client_error(e: Exception) -> bool:
    """Check if exception is a botocore ClientError.

    Uses duck typing to avoid importing botocore at module level.
    """
    return (
        type(e).__name__ == "ClientError"
        and hasattr(e, "response")
        and isinstance(getattr(e, "response", None), dict)
    )


def _get_aws_error_code(e: Exception) -> str:
    """Extract AWS error code from ClientError.

    Returns empty string if error code cannot be extracted.
    """
    try:
        response = getattr(e, "response", {})
        return response.get("Error", {}).get("Code", "")
    except (AttributeError, TypeError):
        return ""


def with_aws_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator for AWS S3/DynamoDB operations with exponential backoff.

    Uses moderate retry settings for AWS service operations.
    Retries on transient errors like throttling, timeouts, and service errors.
    Does not retry on permanent errors like AccessDenied, ValidationException.
    """
    # Import at runtime to avoid dependency on botocore when not using AWS
    try:
        from botocore.exceptions import ClientError, BotoCoreError
    except ImportError:
        # If botocore is not installed, create placeholder exception types
        # that will never match - retry.py can still be imported.
        # WARNING: This means AWS-specific retry (ClientError, BotoCoreError)
        # will be silently disabled. ConnectionError and TimeoutError retries
        # still work because they are built-in Python exceptions.
        ClientError = type("ClientError", (Exception,), {})  # type: ignore
        BotoCoreError = type("BotoCoreError", (Exception,), {})  # type: ignore
        logger.warning(
            "botocore_not_installed_aws_retry_degraded",
            detail=(
                "botocore is not installed; with_aws_retry will not catch "
                "ClientError or BotoCoreError. Only ConnectionError and "
                "TimeoutError will trigger retries."
            ),
        )

    return with_db_retry(
        max_retries=5,
        base_delay=0.1,
        max_delay=2.0,
        backoff_factor=2.0,
        retry_on=(ClientError, BotoCoreError, ConnectionError, TimeoutError),
    )(func)
