from de_pipeline.redact import redact
from de_pipeline.secrets import environment_secrets

SECRET_NAMES = [
    "GITHUB_TOKEN", "GEMINI_API_KEY", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "DB_CONNECTION_STRING", "LICENSE_KEY", "SSH_PRIVATE_KEY", "KUBECONFIG",
    "REGISTRY_AUTH", "SIGNING_CERT", "NPM_AUTH_IDENT", "GPG_PASSPHRASE",
]


def test_every_unknown_variable_is_treated_as_a_secret() -> None:
    env = {name: f"value{i:03d}abcd" for i, name in enumerate(SECRET_NAMES)}
    caught = set(environment_secrets(env))

    leaked = [n for i, n in enumerate(SECRET_NAMES) if f"value{i:03d}abcd" not in caught]

    assert leaked == [], f"these variable names escape redaction: {leaked}"


def test_public_run_metadata_is_not_redacted() -> None:
    env = {"GITHUB_SHA": "4f4cf45abc", "GITHUB_REPOSITORY": "owner/project"}

    assert environment_secrets(env) == []


def test_booleans_and_numbers_are_not_treated_as_secrets() -> None:
    env = {"SOME_FLAG": "true", "SOME_COUNT": "12345", "SOME_VERSION": "1.2.3"}

    assert environment_secrets(env) == []


def test_a_password_in_a_package_index_url_is_collected() -> None:
    env = {"PIP_INDEX_URL": "https://deploy:S3cret-Pa55@pypi.example.com/simple"}

    assert environment_secrets(env) == ["S3cret-Pa55"]


def test_a_plain_index_url_is_not_a_secret() -> None:
    env = {"PIP_INDEX_URL": "https://pypi.example.com/simple"}

    assert environment_secrets(env) == []


def test_the_index_address_stays_readable_in_a_log() -> None:
    env = {"PIP_INDEX_URL": "https://deploy:S3cret-Pa55@pypi.example.com/simple"}
    log = "Looking in indexes: https://pypi.example.com/simple\nauth S3cret-Pa55"

    cleaned = redact(log, environment_secrets(env))

    assert "pypi.example.com/simple" in cleaned
    assert "S3cret-Pa55" not in cleaned
