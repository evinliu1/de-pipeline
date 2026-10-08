import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"
MIN_SECRET_LENGTH = 4
MAX_LINE_CHARS = 4_000

TOKEN_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bgl(?:pat|dt|rt|cbt|ptt|soat|agent|imt|ft)-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bglptt-[0-9a-f]{40}\b"),
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_\-]+"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
]
ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret"
    r"|webhook[_-]?url|private[_-]?token|job[_-]?token|registry[_-]?password)"
    r"\b\s*[:=]\s*[\"']?)([^\s\"']{3,})"
)
BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=\-]{16,}")
URL_CREDENTIALS = re.compile(
    r"(?i)(\b[a-z][a-z0-9+.\-]{0,15}://[^/\s:@]{1,255}:)[^/\s@]{1,255}(@)"
)
DOCKER_LOGIN = re.compile(r"(?i)(--password[ =]+)(\S+)")
VARIABLE_REFERENCE = re.compile(
    r"""^["']?(?:\$\{[A-Za-z_]\w*\}|\$[A-Za-z_]\w*|%[A-Za-z_]\w*%)["']?$"""
)
NEWLINE = "\n"


def clamp_lines(text: str) -> str:
    """Truncates absurdly long lines before any pattern runs.

    A 200 KB single line is a minified bundle or a base64 blob. It carries no
    diagnostic value, and unbounded line length is what lets a regex become a
    denial of service.
    """
    if len(text) <= MAX_LINE_CHARS:
        return text
    out = []
    for line in text.split(NEWLINE):
        if len(line) > MAX_LINE_CHARS:
            cut = len(line) - MAX_LINE_CHARS
            line = line[:MAX_LINE_CHARS] + f" ... [{cut} characters truncated]"
        out.append(line)
    return NEWLINE.join(out)


def hide_value(match: re.Match[str]) -> str:
    """Replaces an assigned value, unless it is only a variable reference.

    ${REGISTRY_PASSWORD} is a name, not a credential, and which variable a job
    authenticated with is often the whole diagnosis. Redacting the name turns
    a findable root cause into an unreadable one.
    """
    if VARIABLE_REFERENCE.match(match.group(2)):
        return match.group(0)
    return match.group(1) + REDACTED


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    text = clamp_lines(text)
    for secret in sorted({s for s in secrets if len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = ASSIGNMENT.sub(hide_value, text)
    text = BEARER.sub(lambda m: m.group(1) + REDACTED, text)
    text = DOCKER_LOGIN.sub(hide_value, text)
    return URL_CREDENTIALS.sub(lambda m: m.group(1) + REDACTED + m.group(2), text)
