from dataclasses import dataclass, field


@dataclass
class FailedJob:
    name: str
    log: str
    failed_steps: list[str] = field(default_factory=list)
    url: str | None = None


@dataclass
class RunFailure:
    jobs: list[FailedJob]
    total_failed_jobs: int
    repo: str | None = None
    workflow: str | None = None
    branch: str | None = None
    sha: str | None = None
    url: str | None = None
    diff: str | None = None
    diff_source: str | None = None