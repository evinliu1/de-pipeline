import sys
import time
from typing import Any

import httpx

from de_pipeline.config import MAX_ATTEMPTS, MAX_WAIT_SECONDS, RETRIABLE_STATUSES


def get_wait(res: httpx.Response | None, attempt: int) -> int:
    backoff = 2 * 2**attempt
    if res is None:
        return min(backoff, MAX_WAIT_SECONDS)
    try:
        wait = int(res.headers.get("Retry-After", backoff))
    except ValueError:
        wait = backoff
    return min(wait, MAX_WAIT_SECONDS)


def request_with_retry(
    method: str, url: str, *, idempotent: bool = True, **kwargs: Any
) -> httpx.Response:
    retry_statuses = RETRIABLE_STATUSES if idempotent else {429}
    retry_errors: tuple[type[httpx.RequestError], ...] = (
        (httpx.RequestError,) if idempotent else (httpx.ConnectError, httpx.ConnectTimeout)
    )

    for attempt in range(MAX_ATTEMPTS):
        is_last = attempt == MAX_ATTEMPTS - 1
        try:
            res = httpx.request(method, url, **kwargs)
        except retry_errors as e:
            if is_last:
                raise
            reason = f"no response ({type(e).__name__})"
            wait = get_wait(None, attempt)
        else:
            if res.status_code not in retry_statuses or is_last:
                return res
            reason = f"status {res.status_code}"
            wait = get_wait(res, attempt)

        print(f"request failed ({reason}), retrying in {wait}s...", file=sys.stderr)
        time.sleep(wait)

    raise AssertionError("unreachable")