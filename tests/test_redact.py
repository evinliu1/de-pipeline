import time

import pytest

from de_pipeline.explain import build_user_message
from de_pipeline.models import FailedJob, RunFailure
from de_pipeline.redact import MAX_LINE_CHARS, REDACTED, clamp_lines, redact

FAKE_SECRETS = [
    "gh" + "p_" + "a1B2" * 9,
    "github" + "_pat_" + "x" * 30,
    "AKIA" + "IOSFODNN7EXAMPLE",
    "AI" + "za" + "S" * 35,
    "xo" + "xb-1234567890-abcdefghij",
    "sk" + "_live_" + "4" * 24,
    "sk" + "-proj-" + "q" * 30,
    "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + ".dGhpc2lzYXNpZ25hdHVyZQ",
]


@pytest.mark.parametrize("secret", FAKE_SECRETS)
def test_known_token_formats_are_redacted(secret: str) -> None:
    redacted = redact(f"using credential {secret} for upload")

    assert secret not in redacted
    assert REDACTED in redacted


def test_private_key_blocks_are_redacted() -> None:
    begin, end = "-----BEGIN " + "RSA PRIVATE KEY-----", "-----END " + "RSA PRIVATE KEY-----"

    redacted = redact(f"key:\n{begin}\nMIIEowIBAAKCAQEA\n{end}\nnext line")

    assert "MIIEowIBAAKCAQEA" not in redacted
    assert redacted.endswith("next line")


def test_assignments_bearer_tokens_and_url_credentials() -> None:
    text = (
        "password=supersecretvalue\n"
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n"
        "cloning https://deploy:hunter2hunter2@git.example.com/repo.git"
    )

    assert redact(text).splitlines() == [
        f"password={REDACTED}",
        f"Authorization: Bearer {REDACTED}",
        f"cloning https://deploy:{REDACTED}@git.example.com/repo.git",
    ]


def test_configured_secrets_are_redacted_but_short_values_are_ignored() -> None:
    redacted = redact("key my-deploy-key-value, abc", ["my-deploy-key-value", "abc"])

    assert redacted == f"key {REDACTED}, abc"


def test_ordinary_text_is_untouched() -> None:
    text = "Ran 42 tests in 1.2s; token count 5; see https://example.com/docs"

    assert redact(text) == text


def test_the_prompt_never_contains_a_secret() -> None:
    token = "gh" + "p_" + "Z9" * 18
    failure = RunFailure(
        jobs=[FailedJob(name="deploy", log=f"error: push rejected for {token}\nusing my-model-key-123")],
        total_failed_jobs=1,
        diff=f"diff --git a/.env b/.env\n+TOKEN={token}",
        diff_source="commit abc1234",
    )

    message = build_user_message(failure, secrets=["my-model-key-123"])

    assert token not in message
    assert "my-model-key-123" not in message

def test_a_short_assigned_password_is_redacted() -> None:
    assert "hunter7" not in redact("password: hunter7")


def test_a_four_character_known_secret_is_redacted() -> None:
    assert "abcd" not in redact("the value is abcd here", ["abcd"])


def test_a_variable_reference_survives_redaction() -> None:
    line = 'docker login --username "${REGISTRY_USER}" --password "${REGISTRY_PASS}" reg.example'

    assert "REGISTRY_PASS" in redact(line)


def test_a_literal_login_password_is_redacted() -> None:
    assert "Hb-7731-admin" not in redact("docker login --password Hb-7731-admin reg.example")


def test_an_assigned_variable_reference_survives() -> None:
    assert "REGISTRY_PASS" in redact("password=$REGISTRY_PASS")


def test_a_windows_variable_reference_survives() -> None:
    assert "REGISTRY_PASS" in redact("--password %REGISTRY_PASS%")


@pytest.mark.parametrize(
    "payload",
    [
        "+x" * 100_000,
        "a" * 200_000,
        "https://" + "a+b." * 50_000,
        ("x" * 200_000 + "\n") * 3,
    ],
    ids=["alternating", "uniform", "scheme-like", "multiline"],
)
def test_redaction_is_fast_on_hostile_input(payload: str) -> None:
    started = time.monotonic()
    redact(payload)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"redaction took {elapsed:.1f}s on hostile input"


def test_a_giant_single_line_is_clamped() -> None:
    out = clamp_lines("y" * 500_000)

    assert len(out) < MAX_LINE_CHARS + 100
    assert "characters truncated" in out


def test_clamping_keeps_a_secret_at_the_start_of_a_long_line() -> None:
    token = "gh" + "p_" + "a1B2" * 9
    line = f"Authorization: token {token} " + "z" * 200_000

    assert token not in redact(line)
