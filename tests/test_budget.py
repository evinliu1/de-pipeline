import time

import pytest

from de_pipeline.config import MAX_DIFF_CHARS, MAX_LOG_CHARS
from de_pipeline.explain import allocate, build_user_message
from de_pipeline.models import FailedJob, RunFailure


@pytest.mark.parametrize(
    "scores",
    [(50, 0, 0), (0, 0, 0), (1, 1, 1), (100, 1, 1), (5, 5, 0)],
)
def test_allocation_never_exceeds_the_cap(scores: tuple[int, ...]) -> None:
    jobs = [
        FailedJob(name=f"j{i}", log="\n".join(["##[error] fatal error"] * s) or "quiet")
        for i, s in enumerate(scores)
    ]

    assert sum(budget for _, budget in allocate(jobs)) <= MAX_LOG_CHARS


def test_allocation_spends_the_whole_budget() -> None:
    jobs = [FailedJob(name=f"j{i}", log="##[error] fatal error") for i in range(3)]

    assert sum(budget for _, budget in allocate(jobs)) == MAX_LOG_CHARS


def test_the_loudest_job_gets_the_largest_share() -> None:
    jobs = [
        FailedJob(name="quiet", log="all fine"),
        FailedJob(name="loud", log="\n".join(["##[error] fatal error"] * 5)),
    ]

    shares = {job.name: budget for job, budget in allocate(jobs)}

    assert shares["loud"] > shares["quiet"]


def test_the_message_respects_both_caps() -> None:
    jobs = [FailedJob(name=f"j{i}", log="x" * 200_000) for i in range(3)]
    failure = RunFailure(
        jobs=jobs, total_failed_jobs=3, diff="diff --git a/a b/a\n" + "+x" * 100_000,
        diff_source="commit",
    )

    assert len(build_user_message(failure, [])) <= MAX_LOG_CHARS + MAX_DIFF_CHARS + 2_000


def test_the_message_says_how_many_jobs_were_left_out() -> None:
    failure = RunFailure(jobs=[FailedJob(name="a", log="x")], total_failed_jobs=4)

    assert "3 not shown" in build_user_message(failure, [])


def test_building_a_message_from_hostile_logs_is_fast() -> None:
    jobs = [FailedJob(name=f"j{i}", log="+x" * 100_000) for i in range(3)]
    failure = RunFailure(jobs=jobs, total_failed_jobs=3)

    started = time.monotonic()
    build_user_message(failure, [])
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"message build took {elapsed:.1f}s"
