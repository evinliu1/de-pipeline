from pathlib import Path

import httpx
import pytest

from de_pipeline import explain, retry
from de_pipeline.errors import ModelError, UsageError
from de_pipeline.explain import RESPONSE_FORMAT_SCHEMA, parse_args, strip_json_fences
from de_pipeline.files import get_file_path
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

    def fake_request(method, url, **kwargs):
        calls.append(url)
        return replies.pop(0)

    monkeypatch.setattr(retry.httpx, "request", fake_request)
    monkeypatch.setattr(retry.time, "sleep", lambda seconds: None)

    assert explain.send_req("not-real-api-key", {"model": "x", "messages": []}) == "Summary: fixed"
    assert len(calls) == 2


def test_send_req_reports_the_last_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = [httpx.Response(503), httpx.Response(500), httpx.Response(502)]
    sleeps = []
    monkeypatch.setattr(retry.httpx, "request", lambda method, url, **kwargs: replies.pop(0))
    monkeypatch.setattr(retry.time, "sleep", sleeps.append)

    with pytest.raises(ModelError, match="502"):
        explain.send_req("not-real-api-key", {"model": "x", "messages": []})

    assert not replies
    assert sleeps == [2, 4]


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


def test_parse_args_reads_a_log_file() -> None:
    assert parse_args(["--log", "ci.log"]).log == Path("ci.log")


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--log", "ci.log", "--run-id", "1"],
        ["--run-id", "not-a-number", "--repo", "a/b"],
    ],
)
def test_parse_args_rejects_bad_input(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_run_id_needs_a_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(SystemExit):
        parse_args(["--run-id", "5"])


def test_repository_defaults_to_the_actions_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "evinliu1/de-pipeline")
    assert parse_args(["--run-id", "5"]).repo == "evinliu1/de-pipeline"