import re
import sys

from de_pipeline import explain


TIMESTAMP_REGEX = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z "
COLOR_REGEX = r"\x1b\[[0-9;]*m"

def strip_timestamps(text: str) -> str:
    return re.sub(TIMESTAMP_REGEX, "", text, flags=re.MULTILINE)

def strip_colors(text: str) -> str:
    return re.sub(COLOR_REGEX, "", text, flags=re.MULTILINE)

def clean_lines(raw: str) -> list[str]:
    timestamps_stripped = strip_timestamps(raw)
    colors_stripped = strip_colors(timestamps_stripped)
    return [line for line in colors_stripped.splitlines() if line.strip()]

def main() -> None:
    file_path = explain.get_file_path(sys.argv)
    file_contents = explain.get_file_contents(file_path)
    clean_lines(file_contents)

if __name__ == "__main__":
    main()