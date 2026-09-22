import re
import sys

from dataclasses import dataclass
from de_pipeline.files import get_file_contents, get_file_path
from de_pipeline.config import MAX_LOG_CHARS

TIMESTAMP_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ")
COLOR_REGEX = re.compile(r"\x1b\[[0-9;]*m")
NOISE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"^##\[endgroup\]",
        r"^remote: (Counting|Compressing|Enumerating|Total)",
        r"^(Receiving|Resolving|Unpacking) (objects|deltas):",
    )
]
FALSE_POSITIVES = re.compile(
    r"\b(0|no|zero) (errors?|failures?|failed)\b"
    r"|\b(errors?|failures?): 0\b"
    r"|continue-on-error",
    re.IGNORECASE,
)
SIGNALS = [
    (re.compile(r"^##\[error\]"), 5),
    (re.compile(r"Traceback \(most recent call last\)"), 4),
    (re.compile(r"^E\s+\S"), 4),
    (re.compile(r"^(FAILED|ERROR)\s+\S"), 4),
    (re.compile(r"\bnpm (ERR!|error)\b"), 4),
    (re.compile(r"^\s*●\s"), 4),
    (re.compile(r"\b(panic|fatal error|segmentation fault|core dumped)\b", re.IGNORECASE), 4),
    (re.compile(r"\b[A-Z][A-Za-z]*(Error|Exception)\b"), 3),
    (re.compile(r"\berror(\[\w+\])?:", re.IGNORECASE), 3),
    (re.compile(r"\berror TS\d+\b"), 3),
    (re.compile(r"^\s*(error|fatal)\b", re.IGNORECASE), 3),
    (re.compile(r"\b(failed|failure|failing)\b", re.IGNORECASE), 2),
    (re.compile(r"\berrors?\b", re.IGNORECASE), 2),
    (re.compile(r"\b(cannot find|could not find|not found|no such file|no module named|unresolved import)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(timed out|timeout|deadline exceeded|ECONNREFUSED|ETIMEDOUT|ECONNRESET)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(permission denied|access denied|unauthorized|forbidden|rate limit)\b", re.IGNORECASE), 2),
    (re.compile(r"\bexit (code|status) [1-9]\d*", re.IGNORECASE), 1),
]
BEFORE = 5
AFTER = 10
TAIL = 20



@dataclass
class Window:
    start: int
    end: int
    score: float

def strip_timestamps(text: str) -> str:
    return TIMESTAMP_REGEX.sub("", text)


def strip_colors(text: str) -> str:
    return COLOR_REGEX.sub("", text)


def is_noise(text: str) -> bool:
    return any(pattern.search(text) for pattern in NOISE_PATTERNS)


def clean_lines(raw: str) -> list[str]:
    cleaned = []
    for line in raw.splitlines():
        text = strip_colors(strip_timestamps(line)).rstrip()
        if not text or is_noise(text):
            continue
        cleaned.append(text)
    return cleaned

def score_line(text: str) -> int:
    if FALSE_POSITIVES.search(text):
        return 0
    highest = 0
    for pattern, score in SIGNALS:
        if pattern.search(text):
            highest = max(highest, score)
    return highest

def extract(raw: str, max_chars: int) -> str:
    lines = clean_lines(raw)
    if not lines:
        return "(no log output)"
    scores = [score_line(line) for line in lines]
    windows = merge(build_windows(scores))
    windows = fit_budget(lines, windows, max_chars)
    return render_windows(lines, windows)

def fit_budget(lines: list[str], windows: list[Window], max_chars: int) -> list[Window]:
    budgeted_windows = []
    total_chars = 0
    windows = sorted(windows, key=lambda window: window.score, reverse=True)
    for window in windows:
        size = sum(1 + len(line) for line in lines[window.start:window.end])
        while size > max_chars:
            window.start += 1
            size = sum(1 + len(line) for line in lines[window.start:window.end])
        if total_chars + size <= max_chars:
            budgeted_windows.append(window)
            total_chars += size

    budgeted_windows = sorted(budgeted_windows, key=lambda window: window.start)
    return budgeted_windows

def merge(windows: list[Window]) -> list[Window]:
    windows = sorted(windows, key=lambda window: window.start)
    merged = []
    for window in windows:
        start = window.start
        end = window.end
        score = window.score
        if merged and start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end,end)
            merged[-1].score = score + merged[-1].score
        else:
            merged.append(Window(start, end, score))
    return merged

def render_windows(lines: list[str], windows: list[Window]) -> str:
    parts = []
    position = 0
    for window in windows:
        if window.start > position:
            omitted = window.start - position
            parts.append(f"... [{omitted} lines omitted] ...")
        parts.extend(lines[window.start:window.end])
        position = window.end
    if position < len(lines):
        omitted = len(lines) - position
        parts.append(f"... [{omitted} lines omitted] ...")
    return "\n".join(parts)

def build_windows(scores: list[int]) -> list[Window]:
    total = len(scores)
    windows = [
        Window(max(0, i - BEFORE), min(total, i + AFTER + 1), float(score))
        for i, score in enumerate(scores)
        if score
    ]
    windows.append(Window(max(0, total - TAIL), total, 1.0))
    return windows

def main() -> None:
    file_path = get_file_path(sys.argv)
    file_contents = get_file_contents(file_path)
    rendered = extract(file_contents, MAX_LOG_CHARS)
    print(rendered)
    


if __name__ == "__main__":
    main()
