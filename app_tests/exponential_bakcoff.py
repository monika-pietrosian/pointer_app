import asyncio
from typing import Iterable, Awaitable, Callable, Any
import logging
import functools
import httpx

logger = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = {429, 502, 503, 504}


number_of_attempts = 0

async def retry_with_backoff(
    fn: Callable[[], Any],
    logger,
    retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
) -> Any:
    """
    Executes 'fn' asynchronously. If it raises exception, retries.

    Up to 'retries' time, multiplying 'delay' by 'backoff_factor' each time
    Raises the final exception if all retries fail
    """
    current_delay = delay
    for attempt in range(retries):
        try:
            logger.info("[retry_with_backoff] Executing attempt %s.", attempt + 1)
            return await fn()
        except Exception as e:

            if attempt == retries - 1:
                logger.warning("[retry_with_backoff] All retries failed.")
                raise e
                
            logger.info("[retry_with_backoff] Attempt failed. Waiting %ss...", current_delay)
            await asyncio.sleep(current_delay)
            current_delay *= backoff_factor



def smart_retry(
        retries: int = 3,
        delay: float = 0.5,
        backoff_factor = 2.0

):
    def decorator(fn: Callable[..., Any]):
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any):
            current_delay = delay
            for attempt in range(retries):
                try:
                    response = await fn(*args, **kwargs)
                    response.raise_for_status()
                    return response
                
                except httpx.HTTPStatusError as err:
                    status_code = e.response.status_code

                    if status_code not in TRANSIENT_STATUS_CODES:
                        logging.error("[%s] Non transient error %s. Failing immediately.", fn.__name__, status_code)
                        raise err
                    
                    elif attempt == retries - 1:
                        logging.warning("[%s] Max retries reached for %s", fn.__name__, status_code)
                        raise err
                    
                    logger.info("[%s] Transient HTTP error %s. Retrying in %s s.", fn.__name__, status_code, current_delay)

                except (httpx.TimeoutException, httpx.NetworkError):

                    if attempt == retries - 1:
                        logging.warning("[%s] Max retries reached for %s", fn.__name__, status_code)
                        raise err
                    
                    logger.info("[%s] Network error %s. Retrying in %s s.", fn.__name__, status_code, current_delay) 

                await asyncio.sleep(current_delay)
                current_delay *= backoff_factor

        return wrapper
    return decorator


async def mock_api_call():
    global number_of_attempts
    number_of_attempts += 1

    if number_of_attempts < 4:
        raise ConnectionError("503 Service Unavailable.")

    return {"status": 200, "data": "OK"}



async def main():

    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
    )

    logger = logging.getLogger(__name__)

    result = await retry_with_backoff(
        fn=mock_api_call,
        logger=logger,
        retries=3,
        delay=1.0,
        backoff_factor=2.0
        )
    if result:
        logger.info("Attempt successfull.")

log = logging.getLogger(__name__)
# Statuses worth a second attempt. 429 included so a Retry-After is honoured;
# 4xx is otherwise a real answer, not a hiccup.
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
    if attempts < 1:
        raise ValueError(f"[{fn.__name__}] Attempts must be >= 1")

    logger = logger or log
    statuses = frozenset(retry_on_status)

    for attempt in range(attempts):
        is_last_attempt = attempt == attempts - 1

        try:
            result = await(fn)
        except RETRYABLE_EXCEPTIONS as exc:
            if is_last_attempt:
                logger.warning(
                                    "[%s] Giving up after %d attempt(s): %s", fn.__name__, attempts, exc.__class__.__name__
                                )
                raise
            wait = _backoff_delay(attempt, base_delay, backoff_factor, max_delay, jitter)
            logger.info(
                "[%s] Attempt %d/%d raised %s; retrying in %.2fs",
                fn.__name__
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
                logger.warning("[%s] Still %s after %d attempts",
                               fn.__name__,
                               status,
                               attempts
                               )
            wait = _retry_after(
                result,
                _backoff_delay(attempt, base_delay, backoff_factor, max_delay, jitter),
            )
            logger.info(
                "[%s] attempt %d/%d returned %s; retrying in %.2fs",
                fn.__name__,
                attempt + 1,
                attempts,
                status,
                wait
            )

        await asyncio.sleep(wait)


if __name__ == "__main__":
    asyncio.run(main())