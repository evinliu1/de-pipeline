"""Write the prompt for a real run to scratch/prompt.txt without calling the model.

Usage: uv run python scratch/try_prompt.py OWNER/NAME RUN_ID
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

from de_pipeline.config import get_env
from de_pipeline.explain import build_user_message
from de_pipeline.github import collect


def main() -> None:
    load_dotenv()
    failure = collect(sys.argv[1], int(sys.argv[2]), get_env("GITHUB_TOKEN"))
    message = build_user_message(failure)
    Path("scratch/prompt.txt").write_text(message, encoding="utf-8")
    print(f"wrote scratch/prompt.txt ({len(message):,} chars)")


if __name__ == "__main__":
    main()
