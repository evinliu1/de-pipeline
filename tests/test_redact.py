import pytest

from de_pipeline.explain import build_user_message
from de_pipeline.models import FailedJob, RunFailure
from de_pipeline.redact import REDACTED, redact

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