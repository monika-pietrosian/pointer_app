"""Async retry helper with exponential backoff, used by the API tests.

Two callers, and they want different things:

* ``conftest.py`` waits for the API to accept connections at session start.
  Until Node finishes booting, every request raises ``httpx.ConnectError``.
* Individual tests wrap a request that could hit a retryable status (429/5xx)
  on a loaded CI runner.

Deliberately *not* retried: ordinary 4xx, ``AssertionError``, and anything else
non-retryable. Retrying a failed assertion only makes a red test slow, and
retrying a 401 hides the bug you were testing for.

Only wrap **idempotent** requests. ``POST /api/students/:id/points`` is
additive, so a retry after a read timeout that actually landed server-side adds
the delta twice.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Awaitable, Callable, Iterable

import httpx

log = logging.getLogger(__name__)

# Statuses worth a second attempt. 
# 429 Too Many Requests, Retry-After included, 4xx is otherwise a code that should fail fast.
# 502 Bad Gateway
# 503 Service Unavailable
# 504 Gateway Timeout
RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})

# httpx.TransportError covers ConnectError, ConnectTimeout, ReadTimeout,
# WriteTimeout, PoolTimeout and RemoteProtocolError -- the boot race and the
# dropped-socket cases. Anything outside this tuple propagates immediately.
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (httpx.TransportError,)

MAX_RETRY_AFTER = 30.0


def _backoff_delay(
    attempt: int,
    base_delay: float,
    backoff_factor: float,
    max_delay: float,
    jitter: bool,
) -> float:
    """Delay before the attempt after ``attempt`` (attempt starting from 0)."""
    exponential_factor = backoff_factor**attempt
    raw_exponential_delay = min(base_delay * exponential_factor, max_delay)
    if not jitter:
        return raw_exponential_delay

    scattered_delay = random.uniform(0, raw_exponential_delay / 2)
    scattered_delay_starting_from_half_a_range = scattered_delay + raw_exponential_delay / 2
    return scattered_delay_starting_from_half_a_range


def _retry_after(response: Any, fallback: float) -> float:
    """If there is a Retry-After header, use the value, otherwise fall back to the backoff."""
    value = getattr(response, "headers", {}).get("retry-after")
    if value is None:
        return fallback
    try:
        return min(float(value), MAX_RETRY_AFTER)
    except (TypeError, ValueError):
        # In case of HTTP-date with an absolute timestamp - Retry-After: Wed, 05 Aug 2026 07:28:00 GMT
        # In the current implementation we are not parsing it and returning the fallback instead.
        return fallback


async def retry_async(
    fn: Callable[[], Awaitable[Any]],
    *,
    attempts: int = 4,
    base_delay: float = 0.25,
    backoff_factor: float = 2.0,
    max_delay: float = 5.0,
    jitter: bool = True,
    retry_on_status: Iterable[int] = RETRYABLE_STATUS_CODES,
    logger: logging.Logger | None = None,
) -> Any:
    """Await ``fn()``, retrying retryable failures with exponential backoff.

    ``attempts`` is the *total* number of tries, not the number of retries
    after the first, so ``attempts=1`` disables retrying.

    Returns whatever ``fn`` returns. If the last attempt still yields a
    retryable status, the response is returned rather than raised -- the caller
    gets to assert on a real status code instead of an opaque retry error. A
    transport error on the last attempt does propagate: there is no response to
    hand back.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    logger = logger or log
    statuses = frozenset(retry_on_status)

    for attempt in range(attempts):
        is_last_attempt = attempt == attempts - 1

        try:
            result = await fn()
        except RETRYABLE_EXCEPTIONS as exc:
            if is_last_attempt:
                logger.warning(
                    "[%s] Giving up after %d attempt(s): %s", fn.__name__, attempts, exc.__class__.__name__
                )
                raise
            wait = _backoff_delay(attempt, base_delay, backoff_factor, max_delay, jitter)
            logger.info(
                "attempt %d/%d raised %s; retrying in %.2fs",
                attempt + 1,
                attempts,
                exc.__class__.__name__,
                wait,
            )
        else:
            status = getattr(result, "status_code", None)
            if status not in statuses:
                return result
            if is_last_attempt:
                logger.warning("still %s after %d attempt(s)", status, attempts)
                return result
            wait = _retry_after(
                result,
                _backoff_delay(attempt, base_delay, backoff_factor, max_delay, jitter),
            )
            logger.info(
                "attempt %d/%d returned %s; retrying in %.2fs",
                attempt + 1,
                attempts,
                status,
                wait,
            )

        await asyncio.sleep(wait)

    raise RuntimeError("unreachable: the loop always returns or raises")


def with_backoff(**retry_kwargs: Any) -> Callable[[Callable], Callable]:
    """Decorator form of :func:`retry_async`.

    Accepts the same keyword arguments::

        @with_backoff(attempts=6)
        async def fetch_students(client):
            return await client.get("/api/students")
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_async(lambda: fn(*args, **kwargs), **retry_kwargs)

        return wrapper

    return decorator
