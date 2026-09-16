import os
import sys
import httpx
import json

from pathlib import Path

from dotenv import load_dotenv

USAGE = "usage: python -m de_pipeline.explain <log-file>"


class DePipelineError(Exception):
    """Base class for expected errors with a message safe to show users."""


class UsageError(DePipelineError):
    """The command was run with the wrong arguments"""


class APIKeyError(DePipelineError):
    """The API key could not be found"""


class LogFileError(DePipelineError):
    """Error reading file contents"""


def get_api_key(key_name: str) -> str:
    api_key = os.getenv(key_name)
    if not api_key:
        raise APIKeyError(
            f"API key {key_name} is missing or not set. Add to .env or export it"
        )
    return api_key


def get_file_path(argv: list[str]) -> Path:
    if len(argv) != 2:
        raise UsageError(USAGE)
    return Path(argv[1])


def get_file_contents(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise LogFileError(f"cannot read {e.filename}: {e.strerror}") from e


def main() -> None:
    load_dotenv()
    try:
        file_path = get_file_path(sys.argv)
        file_contents = get_file_contents(file_path)
        api_key = get_api_key("GEMINI_API_KEY")
    except DePipelineError as e:
        sys.exit(f"error: {e!s}")

    print(file_contents)
    print(bool(api_key))
    print(api_key)

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    headers = {"x-goog-api-key": api_key}
    response = httpx.get(url, headers=headers)
    print(json.dumps(response.json(), indent=2))



if __name__ == "__main__":
    main()
