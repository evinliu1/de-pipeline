from pathlib import Path

import httpx
import pytest

from de_pipeline import explain
from de_pipeline.explain import UsageError, get_file_path

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

    def fake_post(url, **kwargs):
        calls.append(url)
        return replies.pop(0)
    
    monkeypatch.setattr(explain.httpx, "post", fake_post)
    monkeypatch.setattr(explain.time, "sleep", lambda seconds: None)

    assert explain.send_req("fake-key", {"model": "x", "messages": []}) == "Summary: fixed"
    assert len(calls) == 2