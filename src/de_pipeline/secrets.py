import os
import re

MIN_LENGTH = 4
SAFE_NAMES = {
    "COMMENT",
    "DE_PIPELINE_MODEL",
    "GITHUB_ACTION",
    "GITHUB_ACTION_PATH",
    "GITHUB_ACTION_REPOSITORY",
    "GITHUB_ACTIONS",
    "GITHUB_ACTOR",
    "GITHUB_ACTOR_ID",
    "GITHUB_API_URL",
    "GITHUB_BASE_REF",
    "GITHUB_ENV",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_GRAPHQL_URL",
    "GITHUB_HEAD_REF",
    "GITHUB_JOB",
    "GITHUB_OUTPUT",
    "GITHUB_PATH",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_REF_PROTECTED",
    "GITHUB_REF_TYPE",
    "GITHUB_REPOSITORY",
    "GITHUB_REPOSITORY_ID",
    "GITHUB_REPOSITORY_OWNER",
    "GITHUB_REPOSITORY_OWNER_ID",
    "GITHUB_RETENTION_DAYS",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER",
    "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_STATE",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_TRIGGERING_ACTOR",
    "GITHUB_WORKFLOW",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKFLOW_SHA",
    "GITHUB_WORKSPACE",
    "HOME",
    "HOSTNAME",
    "LANG",
    "PATH",
    "PIP_INDEX_URL",
    "PWD",
    "RUN_ID",
    "RUNNER_ARCH",
    "RUNNER_DEBUG",
    "RUNNER_ENVIRONMENT",
    "RUNNER_NAME",
    "RUNNER_OS",
    "RUNNER_TEMP",
    "RUNNER_TOOL_CACHE",
    "SHELL",
    "SHLVL",
    "TERM",
    "TZ",
    "USER",
    "UV_PROJECT_ENVIRONMENT",
}
VALUE_IS_NOISE = re.compile(r"^(?:true|false|yes|no|none|null|\d+(?:\.\d+)*)$", re.IGNORECASE)
URL_PASSWORD = re.compile(
    r"(?i)^[a-z][a-z0-9+.\-]{0,15}://[^/\s:@]{1,255}:([^/\s@]{1,255})@"
)


def is_safe(name: str) -> bool:
    return name in SAFE_NAMES


def environment_secrets(environ: dict[str, str] | None = None) -> list[str]:
    """Every environment value that is not on the safe list.

    An allowlist rather than a denylist: a CI variable this code has never heard
    of is treated as a secret, so a new credential is redacted the day it is
    added rather than the day someone remembers to extend a pattern.

    A safe name can still carry a credential inside a URL, as a package index
    does, so the password is taken from those while the address itself stays
    readable.
    """
    env = os.environ if environ is None else environ
    secrets = []
    for name, value in env.items():
        if is_safe(name):
            embedded = URL_PASSWORD.match(value)
            if embedded and len(embedded.group(1)) >= MIN_LENGTH:
                secrets.append(embedded.group(1))
        elif len(value) >= MIN_LENGTH and not VALUE_IS_NOISE.match(value.strip()):
            secrets.append(value)
    return secrets
