"""Shared retry decorator with exponential backoff for external API calls.

Provides a reusable retry mechanism for ServiceNow, Slack, and AWS Support
API calls that may fail due to connectivity issues.
"""

import functools
import logging
import time
from typing import Callable, Tuple, Type

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0


def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    exceptions: Tuple[Type[BaseException], ...] = (ConnectionError, TimeoutError),
    sleep_func: Callable[[float], None] = time.sleep,
):
    """Decorator that retries a function with exponential backoff on failure.

    Delay formula: base_delay * 2^attempt (e.g. 1s, 2s, 4s for base_delay=1).

    Args:
        max_retries: Maximum number of retry attempts (default 3).
        base_delay: Base delay in seconds before first retry (default 1.0).
        exceptions: Tuple of exception types to catch and retry on.
        sleep_func: Sleep function (injectable for testing).

    Returns:
        Decorated function that retries on specified exceptions.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Attempt %d/%d for %s failed: %s. "
                            "Retrying in %.1fs...",
                            attempt + 1,
                            max_retries + 1,
                            func.__name__,
                            exc,
                            delay,
                        )
                        sleep_func(delay)
                    else:
                        logger.error(
                            "All %d attempts for %s exhausted. Last error: %s",
                            max_retries + 1,
                            func.__name__,
                            exc,
                        )
            raise last_exception

        return wrapper

    return decorator
