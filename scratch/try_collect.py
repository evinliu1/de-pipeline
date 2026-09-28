import sys

from dotenv import load_dotenv

from de_pipeline.config import get_env
from de_pipeline.errors import DePipelineError
from de_pipeline.github import collect


def main() -> None:
    load_dotenv()
    repo, run_id = sys.argv[1], int(sys.argv[2])
    try:
        failure = collect(repo, run_id, get_env("GITHUB_TOKEN"))
    except DePipelineError as e:
        sys.exit(f"error: {e}")

    print(f"workflow:    {failure.workflow}")
    print(f"branch:      {failure.branch}")
    print(f"commit:      {failure.sha[:7]}")
    print(f"failed jobs: {failure.total_failed_jobs}")
    for job in failure.jobs:
        print(f"  {job.name}: failed steps {job.failed_steps}, log {len(job.log):,} chars")
    print(f"diff:        {failure.diff_source}, {len(failure.diff or ''):,} chars")


if __name__ == "__main__":
    main()