import sys
from typing import Any

import httpx

from de_pipeline.config import GITHUB_API, GITHUB_API_VERSION
from de_pipeline.errors import GitHubError, NoFailuresError
from de_pipeline.retry import request_with_retry

JSON = "application/vnd.github+json"
DIFF = "application/vnd.github.diff"
FAILED_CONCLUSIONS = {"failure", "timed_out"}
MAX_JOBS = 3
LOG_UNAVAILABLE = {404, 410}  # missing, or expired after the retention period
DIFF_UNAVAILABLE = {404, 406, 422}  # missing, or too large for GitHub to render
PERMISSIONS = {
    "/actions/": "actions: read",
    "/pulls/": "pull-requests: read",
    "/commits/": "contents: read",
}
from de_pipeline.models import FailedJob, RunFailure


def github_get(
    path: str,
    token: str,
    accept: str = JSON,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """Send a GET request to the GitHub API, raising GitHubError on any failure."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    try:
        res = request_with_retry(
            "GET",
            f"{GITHUB_API}{path}",
            headers=headers,
            params=params,
            follow_redirects=True,
            timeout=30,
        )
    except httpx.RequestError as e:
        raise GitHubError(f"could not reach GitHub ({type(e).__name__})") from e

    if not res.is_success:
        message = github_message(res)
        raise GitHubError(
            f"GitHub request failed ({res.status_code}): {message}"
            f"{permission_hint(path, res.status_code, message)}",
            status=res.status_code,
        )
    return res


def github_message(res: httpx.Response) -> str:
    try:
        return str(res.json()["message"])
    except (ValueError, KeyError, TypeError):
        return res.text or "no details"


def permission_hint(path: str, status: int, message: str) -> str:
    if status != 403 or "rate limit" in message.lower():
        return ""
    for fragment, permission in PERMISSIONS.items():
        if fragment in path:
            return (
                f". In GitHub Actions, grant the workflow the `{permission}` permission"
            )
    return ""


def get_run(repo: str, run_id: int, token: str) -> dict[str, Any]:
    return github_get(f"/repos/{repo}/actions/runs/{run_id}", token).json()


def failed_jobs(repo: str, run_id: int, token: str) -> list[dict[str, Any]]:
    res = github_get(
        f"/repos/{repo}/actions/runs/{run_id}/jobs", token, params={"per_page": 100}
    )
    return [
        job for job in res.json()["jobs"] if job["conclusion"] in FAILED_CONCLUSIONS
    ]


def failed_steps(job: dict[str, Any]) -> list[str]:
    return [
        step["name"]
        for step in job.get("steps", [])
        if step["conclusion"] in FAILED_CONCLUSIONS
    ]


def job_log(repo: str, job_id: int, token: str) -> str | None:
    try:
        return github_get(f"/repos/{repo}/actions/jobs/{job_id}/logs", token).text
    except GitHubError as e:
        if e.status in LOG_UNAVAILABLE:
            return None
        raise


def fetch_diff(path: str, token: str) -> str | None:
    try:
        return github_get(path, token, accept=DIFF).text
    except GitHubError as e:
        if e.status in DIFF_UNAVAILABLE:
            return None
        raise


def get_diff(repo: str, run: dict[str, Any], token: str) -> tuple[str, str] | None:
    pull_requests = run.get("pull_requests") or []
    if pull_requests:
        number = pull_requests[0]["number"]
        diff = fetch_diff(f"/repos/{repo}/pulls/{number}", token)
        if diff is not None:
            return diff, f"pull request #{number}"

    sha = run.get("head_sha")
    if sha:
        diff = fetch_diff(f"/repos/{repo}/commits/{sha}", token)
        if diff is not None:
            return diff, f"commit {sha[:7]}"
    return None


def collect(repo: str, run_id: int, token: str) -> RunFailure:
    run = get_run(repo, run_id, token)
    jobs = failed_jobs(repo, run_id, token)
    if not jobs:
        raise NoFailuresError(f"run {run_id} has no failed jobs to analyze")

    collected = []
    for job in jobs[:MAX_JOBS]:
        log = job_log(repo, job["id"], token)
        if log is None:
            print(
                f"warning: the log for job {job['name']!r} is unavailable",
                file=sys.stderr,
            )
        collected.append(
            FailedJob(
                name=job["name"],
                url=job["html_url"],
                failed_steps=failed_steps(job),
                log=log or "",
            )
        )

    diff = get_diff(repo, run, token)
    return RunFailure(
        repo=repo,
        workflow=run["name"],
        branch=run.get("head_branch"),
        sha=run["head_sha"],
        url=run["html_url"],
        jobs=collected,
        total_failed_jobs=len(jobs),
        diff=diff[0] if diff else None,
        diff_source=diff[1] if diff else None,
    )
