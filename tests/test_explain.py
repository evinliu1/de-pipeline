from pathlib import Path

import httpx
import pytest

from de_pipeline import explain
from de_pipeline.explain import (
    RESPONSE_FORMAT_SCHEMA,
    MAX_ATTEMPTS,
    ModelError,
    UsageError,
    get_file_path,
    get_wait,
    strip_json_fences
)
from de_pipeline.schema import Diagnosis


def test_get_file_path_returns_the_argument() -> None:
    assert get_file_path(["entry1", "log_output.log"]) == Path("log_output.log")


def test_get_file_path_requires_one_argument() -> None:
    with pytest.raises(UsageError):
        get_file_path(["entry1"])


def ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_send_req_retries_a_503_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = [httpx.Response(503), ok("Summary: fixed")]
    calls = []

    def fake_httpx_post(url, **kwargs):
        calls.append(url)
        return replies.pop(0)

    monkeypatch.setattr(explain.httpx, "post", fake_httpx_post)
    monkeypatch.setattr(explain.time, "sleep", lambda seconds: None)

    assert (
        explain.send_req(
            "not-real-api-key", {"model": "not-real-model", "messages": []}
        )
        == "Summary: fixed"
    )
    assert len(calls) == 2


def test_send_req_attempts_3_times_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = [httpx.Response(503), httpx.Response(500), httpx.Response(502)]
    sleeps = []

    def fake_httpx_post(url, **kwargs):
        return replies.pop(0)

    monkeypatch.setattr(explain.httpx, "post", fake_httpx_post)
    monkeypatch.setattr(explain.time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(ModelError, match="502"):
        explain.send_req(
            "not-real-api-key", {"model": "not-real-model", "messages": []}
        )

    assert not replies
    assert sleeps == [2, 4]


def test_get_wait_returns_backoff_if_header_is_date() -> None:
    headers = [
        httpx.Response(429, headers={"Retry-After": "Nov 17 2026 16:22"}),
        httpx.Response(429, headers={"Retry-After": "Nov 18 2026 16:22"}),
        httpx.Response(429, headers={"Retry-After": "Nov 19 2026 16:22"}),
    ]
    backoffs = [2, 4, 8]

    for attempt in range(MAX_ATTEMPTS):
        assert get_wait(headers[attempt], attempt) == backoffs[attempt]


def test_get_wait_caps_at_max_wait() -> None:
    headers = httpx.Response(429, headers={"Retry-After": "350"})
    assert get_wait(headers, 1) == 30
    assert get_wait(None, 10) == 30

def test_schema_matches_the_model() -> None:
    properties = RESPONSE_FORMAT_SCHEMA["json_schema"]["schema"]["properties"]
    assert set(properties) == set(Diagnosis.model_fields)

@pytest.mark.parametrize(
    "text",
    [
        "{'hello': 'world'}",
        "```json\n{'hello': 'world'}\n```",
        "```\n{'hello': 'world'}\n```",
        "  {'hello': 'world'}  ",
    ],
)
def test_strip_json_fences(text: str) -> None:
    assert strip_json_fences(text) == "{'hello': 'world'}"


