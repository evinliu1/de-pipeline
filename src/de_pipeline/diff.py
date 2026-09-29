import re
from dataclasses import dataclass
from pathlib import PurePosixPath

FILE_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)
LOCK_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "uv.lock",
    "pipfile.lock",
    "cargo.lock",
    "gemfile.lock",
    "composer.lock",
    "go.sum",
}
NOISE_SUFFIXES = (".min.js", ".min.css", ".map", ".log")
MAX_NAMES = 15


@dataclass
class FileDiff:
    path: str
    text: str

    @property
    def is_noise(self) -> bool:
        name = PurePosixPath(self.path).name.lower()
        return (
            name in LOCK_FILES
            or name.endswith(NOISE_SUFFIXES)
            or "\nBinary files " in self.text
            or "\nGIT binary patch" in self.text
        )


def split_diff(diff: str) -> list[FileDiff]:
    headers = list(FILE_HEADER.finditer(diff))
    files = []
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(diff)
        text = diff[header.start() : end].rstrip("\n")
        files.append(FileDiff(path=header.group(2), text=text))
    return files


def prepare_diff(diff: str, max_chars: int) -> str:
    files = split_diff(diff)
    if not files:
        return diff[:max_chars]

    noise = [f.path for f in files if f.is_noise]
    changes = sorted((f for f in files if not f.is_noise), key=lambda f: len(f.text))

    parts: list[str] = []
    skipped: list[str] = []
    used = 0
    for f in changes:
        size = len(f.text) + 1
        if used + size <= max_chars:
            parts.append(f.text)
            used += size
        elif not parts:
            parts.append(f.text[:max_chars] + "\n… [rest of this file's changes truncated] …")
            used = max_chars
        else:
            skipped.append(f.path)

    if skipped:
        parts.append(f"… [no room for changes to: {names(skipped)}] …")
    if noise:
        parts.append(f"… [omitted lock, generated, log, and binary files: {names(noise)}] …")
    return "\n".join(parts)


def names(paths: list[str]) -> str:
    shown = ", ".join(paths[:MAX_NAMES])
    extra = len(paths) - MAX_NAMES
    return f"{shown}, and {extra} more" if extra > 0 else shown