import httpx
import pytest

from de_pipeline import retry
from de_pipeline.config import MAX_ATTEMPTS
from de_pipeline.retry import get_wait, request_with_retry

URL = "https://example.test/resource"


def fake_requests(
    monkeypatch: pytest.MonkeyPatch, replies: list[httpx.Response | Exception]
) -> tuple[list[str], list[float]]:
    """Replace httpx.request with replies returned (or raised) in order."""
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        calls.append(method)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(retry.httpx, "request", fake_request)
    monkeypatch.setattr(retry.time, "sleep", sleeps.append)
    return calls, sleeps


def test_server_errors_are_retried_until_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, sleeps = fake_requests(
        monkeypatch, [httpx.Response(503), httpx.Response(502), httpx.Response(200)]
    )

    assert request_with_retry("GET", URL).status_code == 200
    assert len(calls) == 3
    assert sleeps == [2, 4]


def test_the_last_failure_is_returned_without_a_final_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, sleeps = fake_requests(monkeypatch, [httpx.Response(503)] * MAX_ATTEMPTS)

    assert request_with_retry("GET", URL).status_code == 503
    assert sleeps == [2, 4]


def test_other_errors_are_returned_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, sleeps = fake_requests(monkeypatch, [httpx.Response(401)])

    assert request_with_retry("GET", URL).status_code == 401
    assert len(calls) == 1
    assert sleeps == []


def test_network_errors_are_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_requests(monkeypatch, [httpx.ConnectError("refused"), httpx.Response(200)])

    assert request_with_retry("GET", URL).status_code == 200


def test_network_errors_on_every_attempt_are_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_requests(monkeypatch, [httpx.ConnectError("refused")] * MAX_ATTEMPTS)

    with pytest.raises(httpx.ConnectError):
        request_with_retry("GET", URL)


def test_creations_are_not_retried_after_a_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, _ = fake_requests(monkeypatch, [httpx.Response(502)])

    assert request_with_retry("POST", URL, idempotent=False).status_code == 502
    assert len(calls) == 1


def test_creations_are_retried_when_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_requests(monkeypatch, [httpx.Response(429), httpx.Response(201)])

    assert request_with_retry("POST", URL, idempotent=False).status_code == 201


def test_creations_are_not_retried_after_a_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_requests(monkeypatch, [httpx.ReadTimeout("the server may have acted")])

    with pytest.raises(httpx.ReadTimeout):
        request_with_retry("POST", URL, idempotent=False)


@pytest.mark.parametrize(("attempt", "expected"), [(0, 2), (1, 4), (2, 8)])
def test_get_wait_falls_back_to_backoff_when_the_header_is_a_date(
    attempt: int, expected: int
) -> None:
    res = httpx.Response(429, headers={"Retry-After": "Nov 17 2026 16:22"})
    assert get_wait(res, attempt) == expected


def test_get_wait_caps_at_max_wait() -> None:
    assert get_wait(httpx.Response(429, headers={"Retry-After": "350"}), 1) == 30
    assert get_wait(None, 10) == 31