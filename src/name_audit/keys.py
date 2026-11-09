"""Read API keys from an env file without loading anything else from it."""

import os
from pathlib import Path

KEY_NAMES = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def read_key(provider: str, env_file: Path | None) -> str:
    """Return the key for a provider from the environment or one line of the env file.

    Only the line that starts with the key's own variable name is kept; every other
    line is skipped unread into any variable.
    """
    var = KEY_NAMES[provider]
    if os.environ.get(var):
        return os.environ[var]
    if env_file is None:
        raise SystemExit(f"{var} is not set and no env file was given")
    prefix = f"{var}="
    with env_file.open() as fh:
        for line in fh:
            if line.startswith(prefix) or line.startswith(f"export {prefix}"):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value:
                    return value
    raise SystemExit(f"{var} was not found in {env_file}")
