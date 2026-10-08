import re
import sys
from dataclasses import dataclass

from de_pipeline.config import MAX_LOG_CHARS
from de_pipeline.files import get_file_contents, get_file_path

TIMESTAMP_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ")
COLOR_REGEX = re.compile(r"\x1b\[[0-9;]*m")
NOISE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"^##\[endgroup\]",
        r"^remote: (Counting|Compressing|Enumerating|Total)",
        r"^(Receiving|Resolving|Unpacking) (objects|deltas):",
        r"^\[INFO\] (Downloading|Downloaded|Progress) ",
        r"^Progress \(\d+\):",
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
    (re.compile(r"\b(OOMKilled|out of memory|no space left on device)\b", re.IGNORECASE), 5),
    (re.compile(r"\bexit (code|status) 137\b"), 5),
    (re.compile(r"^\[ERROR\]"), 4),
    (re.compile(r"\b(BUILD FAILURE|Failed to execute goal)\b"), 4),
    (re.compile(r"\bError: (UPGRADE|INSTALLATION|UNINSTALL) FAILED\b"), 4),
    (re.compile(r"\b(manifest unknown|unauthorized: authentication required|denied: requested access)\b"), 4),
    (re.compile(r"\b(ImagePullBackOff|CrashLoopBackOff|ErrImagePull)\b"), 4),
    (re.compile(r"\b(Cannot connect to the Docker daemon|connection refused)\b", re.IGNORECASE), 3),
    (re.compile(r"^\S+:\d+:\d+: [EWFC]\d+ "), 3),
    (re.compile(r"Traceback \(most recent call last\)"), 4),
    (re.compile(r"^E\s+\S"), 4),
    (re.compile(r"^(FAILED|ERROR)\s+\S"), 4),
    (re.compile(r"\bnpm (ERR!|error)\b"), 4),
    (re.compile(r"^\s*●\s"), 4),
    (
        re.compile(
            r"\b(panic|fatal error|segmentation fault|core dumped)\b", re.IGNORECASE
        ),
        4,
    ),
    (re.compile(r"\b[A-Z][A-Za-z]*(Error|Exception)\b"), 3),
    (re.compile(r"\berror(\[\w+\])?:", re.IGNORECASE), 3),
    (re.compile(r"\berror TS\d+\b"), 3),
    (re.compile(r"^\s*(error|fatal)\b", re.IGNORECASE), 3),
    (re.compile(r"\b(failed|failure|failing)\b", re.IGNORECASE), 2),
    (re.compile(r"\berrors?\b", re.IGNORECASE), 2),
    (
        re.compile(
            r"\b(cannot find|could not find|not found|no such file|no module named|unresolved import)\b",
            re.IGNORECASE,
        ),
        2,
    ),
    (
        re.compile(
            r"\b(timed out|timeout|deadline exceeded|ECONNREFUSED|ETIMEDOUT|ECONNRESET)\b",
            re.IGNORECASE,
        ),
        2,
    ),
    (
        re.compile(
            r"\b(permission denied|access denied|unauthorized|forbidden|rate limit)\b",
            re.IGNORECASE,
        ),
        2,
    ),
    (re.compile(r"\bexit (code|status) [1-9]\d*", re.IGNORECASE), 1),
]
BEFORE = 5
AFTER = 10
TAIL = 20
SEPARATOR_CHARS = 30
MIN_WINDOW_LINES = 3
SIGNAL_SAMPLE = 10


@dataclass
class Window:
    start: int
    end: int
    score: float
    anchor: int | None = None

    def __post_init__(self) -> None:
        if self.anchor is None:
            self.anchor = self.start


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


def signal_score(raw: str) -> int:
    scores = sorted((score_line(line) for line in clean_lines(raw)), reverse=True)
    return sum(scores[:SIGNAL_SAMPLE])


def extract(raw: str, max_chars: int) -> str:
    lines = clean_lines(raw)
    if not lines:
        return "(no log output)"
    scores = [score_line(line) for line in lines]
    windows = merge(build_windows(scores))
    windows = fit_budget(lines, windows, max_chars)
    return render_windows(lines, windows)


def measure(lines: list[str], start: int, end: int) -> int:
    return sum(1 + len(lines[index]) for index in range(start, end))


def shrink(lines: list[str], window: Window, max_chars: int) -> Window | None:
    """Trims a window inward toward its anchor until it fits.

    The anchor is the line that earned the window its score, so it is the last
    line to go. A signal window carries its anchor five lines in; the tail
    window carries it on the final line. Trimming from a fixed side would throw
    away the decisive line of one or the other.
    """
    start, end = window.start, window.end
    anchor = min(max(window.anchor or 0, start), end - 1)
    size = measure(lines, start, end)
    while size > max_chars and end - start > 1:
        if end - 1 > anchor:
            end -= 1
            size -= len(lines[end]) + 1
        elif start < anchor:
            size -= len(lines[start]) + 1
            start += 1
        else:
            break
    if size > max_chars:
        return None
    return Window(start, end, window.score, anchor)


def fit_budget(lines: list[str], windows: list[Window], max_chars: int) -> list[Window]:
    budgeted_windows: list[Window] = []
    total_chars = 0
    for window in sorted(windows, key=lambda window: window.score, reverse=True):
        separator = SEPARATOR_CHARS if budgeted_windows else 0
        fitted = shrink(lines, window, max_chars - total_chars - separator)
        if fitted is None:
            continue
        was_trimmed = fitted.end - fitted.start < window.end - window.start
        if was_trimmed and budgeted_windows and fitted.end - fitted.start < MIN_WINDOW_LINES:
            continue
        budgeted_windows.append(fitted)
        total_chars += separator + measure(lines, fitted.start, fitted.end)

    return sorted(budgeted_windows, key=lambda window: window.start)


def merge(windows: list[Window]) -> list[Window]:
    merged: list[Window] = []
    strongest: list[float] = []
    for window in sorted(windows, key=lambda window: window.start):
        if merged and window.start <= merged[-1].end:
            if window.score > strongest[-1]:
                merged[-1].anchor = window.anchor
                strongest[-1] = window.score
            merged[-1].end = max(merged[-1].end, window.end)
            merged[-1].score = window.score + merged[-1].score
        else:
            merged.append(Window(window.start, window.end, window.score, window.anchor))
            strongest.append(window.score)
    return merged


def render_windows(lines: list[str], windows: list[Window]) -> str:
    parts = []
    position = 0
    for window in windows:
        if window.start > position:
            omitted = window.start - position
            parts.append(f"... [{omitted} lines omitted] ...")
        parts.extend(lines[window.start : window.end])
        position = window.end
    if position < len(lines):
        omitted = len(lines) - position
        parts.append(f"... [{omitted} lines omitted] ...")
    return "\n".join(parts)


def build_windows(scores: list[int]) -> list[Window]:
    total = len(scores)
    windows = [
        Window(max(0, i - BEFORE), min(total, i + AFTER + 1), float(score), i)
        for i, score in enumerate(scores)
        if score
    ]
    windows.append(Window(max(0, total - TAIL), total, 1.0, max(0, total - 1)))
    return windows


def main() -> None:
    file_path = get_file_path(sys.argv)
    file_contents = get_file_contents(file_path)
    rendered = extract(file_contents, MAX_LOG_CHARS)
    print(rendered)


if __name__ == "__main__":
    main()
