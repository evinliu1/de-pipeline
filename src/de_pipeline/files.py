from pathlib import Path

from de_pipeline.errors import LogFileError, UsageError

USAGE = "usage: python -m de_pipeline.explain <log-file>"


def get_file_path(argv: list[str]) -> Path:
    if len(argv) != 2:
        raise UsageError(USAGE)
    return Path(argv[1])


def get_file_contents(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise LogFileError(f"cannot read {e.filename}: {e.strerror}") from e
