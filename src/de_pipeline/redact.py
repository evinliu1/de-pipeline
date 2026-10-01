import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"
MIN_SECRET_LENGTH = 8

TOKEN_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
]
ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)"
    r"\b\s*[:=]\s*[\"']?)([^\s\"']{8,})"
)
BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=\-]{16,}")
URL_CREDENTIALS = re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:)[^/\s@]+(@)")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    for secret in sorted({s for s in secrets if len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = ASSIGNMENT.sub(lambda m: m.group(1) + REDACTED, text)
    text = BEARER.sub(lambda m: m.group(1) + REDACTED, text)
    return URL_CREDENTIALS.sub(lambda m: m.group(1) + REDACTED + m.group(2), text)