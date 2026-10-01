import httpx
import pytest

from de_pipeline import github, retry
from de_pipeline.errors import GitHubError, NoFailuresError

REPO = "evinliu1/de-pipeline"
API = "https://api.github.com"
RUN_PATH = f"/repos/{REPO}/actions/runs/1"
JOBS_PATH = f"{RUN_PATH}/jobs"
LOG_PATH = f"/repos/{REPO}/actions/jobs/11/logs"
COMMIT_PATH = f"/repos/{REPO}/commits/abc1234def"
PR_PATH = f"/repos/{REPO}/pulls/7"


def job(job_id: int, name: str, conclusion: str) -> dict[str, object]:
    return {
        "id": job_id,
        "name": name,
        "conclusion": conclusion,
        "html_url": f"https://github.com/{REPO}/actions/runs/1/job/{job_id}",
        "steps": [
            {"name": "Checkout", "conclusion": "success"},
            {"name": "Run tests", "conclusion": conclusion},
        ],
    }


def run(pull_requests: list[dict[str, int]] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "name": "CI",
            "head_sha": "abc1234def",
            "head_branch": "main",
            "html_url": "https://github.com/run/1",
            "pull_requests": pull_requests or [],
        },
    )


def routes() -> dict[str, httpx.Response]:
    """A failed run with one failed job, its log, and a commit diff."""
    return {
        RUN_PATH: run(),
        JOBS_PATH: httpx.Response(
            200, json={"jobs": [job(11, "unit-tests", "failure"), job(12, "lint", "success")]}
        ),
        LOG_PATH: httpx.Response(200, text="E   assert 3 == 2"),
        COMMIT_PATH: httpx.Response(200, text="diff --git a/src/app.py b/src/app.py"),
    }


def fake_github(monkeypatch: pytest.MonkeyPatch, table: dict[str, httpx.Response]) -> list[str]:
    """Answer each request from the table by path, and record the paths requested."""
    requested: list[str] = []

    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        path = url.removeprefix(API)
        requested.append(path)
        return table.get(path, httpx.Response(404, json={"message": "Not Found"}))

    monkeypatch.setattr(retry.httpx, "request", fake_request)
    monkeypatch.setattr(retry.time, "sleep", lambda seconds: None)
    return requested


def test_collect_gathers_failed_jobs_logs_and_the_commit_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_github(monkeypatch, routes())

    failure = github.collect(REPO, 1, "fake-token")

    assert failure.workflow == "CI"
    assert failure.total_failed_jobs == 1
    assert [job.name for job in failure.jobs] == ["unit-tests"]
    assert failure.jobs[0].failed_steps == ["Run tests"]
    assert failure.jobs[0].log == "E   assert 3 == 2"
    assert failure.diff_source == "commit abc1234"


def test_collect_prefers_the_pull_request_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    table = routes()
    table[RUN_PATH] = run([{"number": 7}])
    table[PR_PATH] = httpx.Response(200, text="diff --git a/pr.py b/pr.py")
    requested = fake_github(monkeypatch, table)

    failure = github.collect(REPO, 1, "fake-token")

    assert failure.diff_source == "pull request #7"
    assert COMMIT_PATH not in requested
    assert failure.pull_request == 7


def test_collect_falls_back_when_the_pull_request_diff_is_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = routes()
    table[RUN_PATH] = run([{"number": 7}])
    table[PR_PATH] = httpx.Response(406, json={"message": "diff too large"})
    fake_github(monkeypatch, table)

    assert github.collect(REPO, 1, "fake-token").diff_source == "commit abc1234"


def test_collect_survives_an_expired_log(monkeypatch: pytest.MonkeyPatch) -> None:
    table = routes()
    table[LOG_PATH] = httpx.Response(410)
    fake_github(monkeypatch, table)

    assert github.collect(REPO, 1, "fake-token").jobs[0].log == ""


def test_collect_without_failed_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    table = routes()
    table[JOBS_PATH] = httpx.Response(200, json={"jobs": [job(12, "lint", "success")]})
    fake_github(monkeypatch, table)

    with pytest.raises(NoFailuresError):
        github.collect(REPO, 1, "fake-token")


def test_a_missing_run_reports_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    table = routes()
    del table[RUN_PATH]
    fake_github(monkeypatch, table)

    with pytest.raises(GitHubError) as caught:
        github.collect(REPO, 1, "fake-token")
    assert caught.value.status == 404


def test_a_forbidden_request_names_the_missing_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    table = routes()
    table[JOBS_PATH] = httpx.Response(403, json={"message": "Resource not accessible by integration"})
    fake_github(monkeypatch, table)

    with pytest.raises(GitHubError, match="actions: read"):
        github.collect(REPO, 1, "fake-token")


COMMENTS_PATH = f"/repos/{REPO}/issues/7/comments"


def fake_api(
    monkeypatch: pytest.MonkeyPatch, table: dict[tuple[str, str], httpx.Response]
) -> list[tuple[str, str, object]]:
    """Answer each request by method and path, and record what was sent."""
    sent: list[tuple[str, str, object]] = []

    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        path = url.removeprefix(API)
        sent.append((method, path, kwargs.get("json")))
        return table.get((method, path), httpx.Response(404, json={"message": "Not Found"}))

    monkeypatch.setattr(retry.httpx, "request", fake_request)
    monkeypatch.setattr(retry.time, "sleep", lambda seconds: None)
    return sent


def test_upsert_creates_a_comment_when_none_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_api(
        monkeypatch,
        {
            ("GET", COMMENTS_PATH): httpx.Response(200, json=[]),
            ("POST", COMMENTS_PATH): httpx.Response(201, json={"html_url": "https://github.com/c/1"}),
        },
    )

    assert github.upsert_comment(REPO, 7, "body", "fake-token") == "https://github.com/c/1"
    method, _, payload = sent[-1]
    assert method == "POST"
    assert payload["body"].startswith(github.COMMENT_MARKER)


def test_upsert_edits_the_earlier_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_api(
        monkeypatch,
        {
            ("GET", COMMENTS_PATH): httpx.Response(
                200,
                json=[
                    {"id": 3, "body": "unrelated"},
                    {"id": 9, "body": f"{github.COMMENT_MARKER}\nold diagnosis"},
                ],
            ),
            ("PATCH", f"/repos/{REPO}/issues/comments/9"): httpx.Response(
                200, json={"html_url": "https://github.com/c/9"}
            ),
        },
    )

    assert github.upsert_comment(REPO, 7, "new", "fake-token") == "https://github.com/c/9"
    assert [method for method, _, _ in sent] == ["GET", "PATCH"]


def test_a_failed_comment_is_not_posted_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_api(
        monkeypatch,
        {
            ("GET", COMMENTS_PATH): httpx.Response(200, json=[]),
            ("POST", COMMENTS_PATH): httpx.Response(502),
        },
    )

    with pytest.raises(GitHubError):
        github.upsert_comment(REPO, 7, "body", "fake-token")
    assert [method for method, _, _ in sent].count("POST") == 1


def test_a_forbidden_comment_names_the_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_api(
        monkeypatch,
        {
            ("GET", COMMENTS_PATH): httpx.Response(200, json=[]),
            ("POST", COMMENTS_PATH): httpx.Response(
                403, json={"message": "Resource not accessible by integration"}
            ),
        },
    )

    with pytest.raises(GitHubError, match="pull-requests: write"):
        github.upsert_comment(REPO, 7, "body", "fake-token")