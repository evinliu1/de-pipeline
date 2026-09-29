from de_pipeline.diff import prepare_diff, split_diff

CODE = "diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2"
LOCK = "diff --git a/uv.lock b/uv.lock\n--- a/uv.lock\n+++ b/uv.lock\n@@ -1 +1 @@\n-v1\n+v2"
LOG = "diff --git a/tests/fixtures/ci.log b/tests/fixtures/ci.log\n" + "+log line\n" * 500
BINARY = "diff --git a/logo.png b/logo.png\nindex 1..2 100644\nBinary files a/logo.png and b/logo.png differ"
BIG = "diff --git a/src/big.py b/src/big.py\n" + "+pass\n" * 1_000


def test_split_diff_finds_each_file() -> None:
    files = split_diff("\n".join([CODE, LOCK, BINARY]))

    assert [f.path for f in files] == ["src/app.py", "uv.lock", "logo.png"]
    assert [f.is_noise for f in files] == [False, True, True]


def test_prepare_diff_keeps_code_and_names_what_it_dropped() -> None:
    prepared = prepare_diff("\n".join([LOCK, LOG, CODE, BINARY]), max_chars=5_000)

    assert "+x = 2" in prepared
    assert "-v1" not in prepared
    assert "log line" not in prepared
    assert "uv.lock" in prepared


def test_prepare_diff_prefers_small_files_when_space_is_short() -> None:
    prepared = prepare_diff("\n".join([BIG, CODE]), max_chars=500)

    assert "+x = 2" in prepared
    assert "no room for changes to: src/big.py" in prepared


def test_prepare_diff_truncates_a_single_oversized_file() -> None:
    prepared = prepare_diff(BIG, max_chars=500)

    assert prepared.startswith("diff --git a/src/big.py")
    assert "truncated" in prepared


def test_prepare_diff_of_non_git_text() -> None:
    assert prepare_diff("plain text", max_chars=5) == "plain"