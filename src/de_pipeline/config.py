import os

from de_pipeline.errors import EnvError

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 30
RETRIABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_LOG_CHARS = 20_000


def get_env(key_name: str) -> str:
    val = os.getenv(key_name)
    if not val:
        raise EnvError(
            f"Env var {key_name} is missing or not set. Add to .env or export it"
        )
    return val
