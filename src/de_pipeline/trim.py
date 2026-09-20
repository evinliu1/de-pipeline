import re
import sys

from de_pipeline import explain


TIMESTAMP_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ")
COLOR_REGEX = re.compile(r"\x1b\[[0-9;]*m")
NOISE_PATTERNS = [
    r"^##\[endgroup\]",
    r"^remote: (Counting|Compressing|Enumerating|Total)",
    r"^(Receiving|Resolving|Unpacking) (objects|deltas):",
]
NOISE_PATTERNS_REGEX = [re.compile(p) for p in NOISE_PATTERNS]

def strip_timestamps(text: str) -> str:
    return re.sub(TIMESTAMP_REGEX, "", text)

def strip_colors(text: str) -> str:
    return re.sub(COLOR_REGEX, "", text)

def is_noise(text: str) -> bool:
    for pattern in NOISE_PATTERNS_REGEX:
        if re.search(pattern, text):
            return True
    return False

def clean_lines(raw: str) -> list[str]:
    cleaned = []
    for line in raw.splitlines():
        timestamps_stripped = strip_timestamps(line)
        colors_stripped = strip_colors(timestamps_stripped)
        if not line.strip() or is_noise(colors_stripped):
            continue
        trialing_stripped = colors_stripped.rstrip()
        cleaned.append(trialing_stripped)
    return cleaned

def main() -> None:
    file_path = explain.get_file_path(sys.argv)
    file_contents = explain.get_file_contents(file_path)
    for line in clean_lines(file_contents):
        print(line)

if __name__ == "__main__":
    main()