from pathlib import Path

import pytest

from de_pipeline.config import MAX_LOG_CHARS
from de_pipeline.trim import (
    Window,
    build_windows,
    clean_lines,
    extract,
    fit_budget,
    merge,
    render_windows,
    score_line
)

FIXTURES = Path(__file__).parent / "fixtures"

def omitted(count: int) -> str:
    return f"... [{count} lines omitted] ..."

def test_clean_lines_removes_timestamps() -> None:
    assert clean_lines("2026-09-14T10:00:12.1234567Z hello") == ["hello"]

def test_clean_lines_removes_color_codes() -> None:
    assert clean_lines("\x1b[31mFAILED\x1b[0m test_a") == ["FAILED test_a"]

def test_clean_lines_drops_blank_lines_and_trailing_whitespace() -> None:
    assert clean_lines("hello   \n\n   \nworld") == ["hello", "world"]

@pytest.mark.parametrize(
    "noise",
    [
        "##[endgroup]",
        "remote: Counting objects: 100% (5/5), done.",
        "Receiving objects: 100% (5/5), done."
    ]
)
def test_clean_lines_drops_noise(noise: str) -> None:
    assert clean_lines(noise) == []


def test_clean_lines_drops_timestamp_only_lines() -> None:
    assert clean_lines("2026-09-14T10:00:12.1234567Z ") == []


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("##[error]Process completed with exit code 1.", 5),
        ("E       AssertionError: assert 2 == 3", 4),
        ("FAILED samples/test_fail.py::test_math", 4),
        ("Traceback (most recent call last):", 4),
        ("TypeError: unsupported operand type", 3),
        ("error: cannot find module 'foo'", 3),
        ("2 failed, 41 passed in 1.23s", 2),
        ("Process completed with exit code 1.", 1),
        ("Process completed with exit code 0.", 0),
        ("Found 0 errors in 12 files", 0),
        ("lint: no errors", 0),
        ("Collecting pytest>=8", 0),
    ],
)
def test_score_line(line: str, expected: int) -> None:
    assert score_line(line) == expected


def test_build_windows_surrounds_each_signal_and_adds_the_tail() -> None:
    scores = [0] * 30
    scores[12] = 4
    scores[15] = 3

    assert build_windows(scores) == [
        Window(7, 23, 4.0),
        Window(10, 26, 3.0),
        Window(10, 30, 1.0),
    ]

def test_build_windows_clamps_at_the_start_of_the_log() -> None:
    scores = [5] + [0] * 29

    assert build_windows(scores)[0] == Window(0, 11, 5.0)


def test_build_windows_without_signals_returns_only_the_tail() -> None:
    assert build_windows([0] * 10) == [Window(0, 10, 1.0)]


def test_merge_combines_overlapping_windows_and_adds_scores() -> None:
    windows = [Window(0, 10, 2.0), Window(5, 15, 3.0), Window(40, 50, 1.0)]

    assert merge(windows) == [Window(0, 15, 5.0), Window(40, 50, 1.0)]


def test_merge_combines_touching_windows() -> None:
    assert merge([Window(0, 10, 1.0), Window(10, 20, 1.0)]) == [Window(0, 20, 2.0)]


def test_merge_handles_unsorted_input() -> None:
    # build_windows appends the tail last, and it can start before the window ahead of it.
    assert merge([Window(85, 100, 4.0), Window(80, 100, 1.0)]) == [Window(80, 100, 5.0)]


def test_merge_does_not_change_its_input() -> None:
    windows = [Window(0, 10, 2.0), Window(5, 15, 3.0)]

    merge(windows)

    assert windows == [Window(0, 10, 2.0), Window(5, 15, 3.0)]


def test_merge_of_nothing_is_nothing() -> None:
    assert merge([]) == []


def test_fit_budget_keeps_everything_that_fits_in_log_order() -> None:
    lines = ["x" * 9] * 20
    windows = [Window(10, 11, 9.0), Window(0, 1, 1.0)]

    assert fit_budget(lines, windows, 1_000) == [Window(0, 1, 1.0), Window(10, 11, 9.0)]


def test_fit_budget_prefers_the_higher_score() -> None:
    lines = ["x" * 99] * 20  # each line costs 100 characters, including its newline
    windows = [Window(0, 1, 1.0), Window(10, 11, 5.0)]

    assert fit_budget(lines, windows, 150) == [Window(10, 11, 5.0)]


def test_fit_budget_skips_a_window_that_does_not_fit_but_keeps_a_smaller_one() -> None:
    lines = ["x" * 99] * 21
    windows = [Window(0, 10, 5.0), Window(10, 20, 3.0), Window(20, 21, 1.0)]

    assert fit_budget(lines, windows, 1_100) == [Window(0, 10, 5.0), Window(20, 21, 1.0)]


def test_fit_budget_keeps_the_end_of_an_oversized_window() -> None:
    lines = ["x" * 99] * 100

    assert fit_budget(lines, [Window(0, 100, 1.0)], 1_000) == [Window(90, 100, 1.0)]


LINES = [f"line {i}" for i in range(10)]


def test_render_windows_marks_every_gap() -> None:
    windows = [Window(2, 4, 1.0), Window(6, 8, 1.0)]

    assert render_windows(LINES, windows) == "\n".join(
        [omitted(2), "line 2", "line 3", omitted(2), "line 6", "line 7", omitted(2)]
    )


def test_render_windows_without_gaps_has_no_markers() -> None:
    assert render_windows(LINES, [Window(0, 10, 1.0)]) == "\n".join(LINES)


def test_render_windows_starting_at_the_first_line() -> None:
    assert render_windows(LINES, [Window(0, 3, 1.0)]) == "\n".join(
        ["line 0", "line 1", "line 2", omitted(7)]
    )


def test_extract_keeps_the_error_and_drops_setup() -> None:
    lines = [f"setup step {i}" for i in range(200)]
    lines[150] = "E       AssertionError: assert 2 == 3"

    excerpt = extract("\n".join(lines), max_chars=10_000).splitlines()

    assert "E       AssertionError: assert 2 == 3" in excerpt
    assert "setup step 10" not in excerpt
    assert omitted(145) in excerpt


def test_extract_without_signals_keeps_the_tail() -> None:
    lines = [f"step {i}" for i in range(100)]

    excerpt = extract("\n".join(lines), max_chars=10_000).splitlines()

    assert excerpt[0] == omitted(80)
    assert excerpt[-1] == "step 99"
    assert "step 79" not in excerpt


def test_extract_respects_the_budget() -> None:
    lines = [f"step {i}" for i in range(2_000)]
    for i in range(0, 2_000, 100):
        lines[i] = "error: step failed"

    excerpt = extract("\n".join(lines), max_chars=1_000)

    assert "error: step failed" in excerpt
    # Omission markers are added after budgeting, so allow room for them.
    assert len(excerpt) <= 1_000 + 30 * excerpt.count("lines omitted")


@pytest.mark.parametrize("raw", ["", "\n\n   \n"])
def test_extract_of_an_empty_log(raw: str) -> None:
    assert extract(raw, max_chars=1_000) == "(no log output)"


def test_extract_keeps_the_assertion_from_a_real_ci_log() -> None:
    raw = (FIXTURES / "ci.log").read_text(encoding="utf-8")

    assert "assert 3 == 2" in extract(raw, max_chars=MAX_LOG_CHARS)