"""
Retry wrapper for LLM invocations.

Model-serving endpoints intermittently throttle (429) or time out under
load. Without a retry policy, a single transient blip fails an entire
invoice (and, before the batch-level fix in ``runner.py``, could fail
the whole job). This wraps any zero-arg callable with exponential
backoff + jitter, capped at ``config.max_retries`` attempts.

Kept as a tiny standalone module (rather than reaching for a full
`tenacity` dependency) so the pipeline's retry behavior has no extra
third-party surface to security-scan or version-pin.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Errors worth retrying: network hiccups, timeouts, and rate limits.
# Anything else (bad prompt, auth failure) should fail fast instead of
# silently burning retry budget.
_RETRYABLE_EXCEPTION_NAMES = (
    "Timeout",
    "ConnectionError",
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "ServiceUnavailableError",
)


def _is_retryable(exc: BaseException) -> bool:
    return type(exc).__name__ in _RETRYABLE_EXCEPTION_NAMES or isinstance(exc, (TimeoutError, ConnectionError))


def with_retry(
    func: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 20.0,
    retryable: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Call ``func()`` with exponential backoff + full jitter.

    Retries up to ``max_retries`` additional times (so ``max_retries=3``
    means up to 4 total attempts) only for exceptions that look
    transient (see ``_is_retryable``); anything else propagates
    immediately on the first failure.
    """
    attempt = 0
    while True:
        try:
            return func()
        except retryable as exc:  # noqa: BLE001 - deliberately broad, filtered by _is_retryable below
            attempt += 1
            if attempt > max_retries or not _is_retryable(exc):
                raise
            delay = min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))
            jittered_delay = random.uniform(0, delay)  # noqa: S311 - jitter, not security-sensitive
            logger.warning(
                "Retryable error on attempt %s/%s (%s: %s); backing off %.2fs",
                attempt,
                max_retries,
                type(exc).__name__,
                exc,
                jittered_delay,
            )
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(jittered_delay)


def retryable(max_retries: int = 3, base_delay_seconds: float = 1.0, max_delay_seconds: float = 20.0):
    """Decorator form of ``with_retry`` for functions taking no meaningful
    args to vary between retries (i.e. the call itself is idempotent)."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return with_retry(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                base_delay_seconds=base_delay_seconds,
                max_delay_seconds=max_delay_seconds,
            )

        return wrapper

    return decorator
