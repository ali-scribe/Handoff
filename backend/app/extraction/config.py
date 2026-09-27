"""Environment-based Gemini configuration: API key name, model, and timeout settings."""

import os
from dataclasses import dataclass, field

from app.extraction.errors import MissingApiKeyError, ProviderFailureError

# Environment variable NAMES (Req 15.1). Values live only in the environment
# / a local .env, never in source (Req 15.2).
ENV_API_KEY = "GEMINI_API_KEY"
ENV_MODEL = "GEMINI_MODEL"
ENV_TIMEOUT = "GEMINI_TIMEOUT_SECONDS"

DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class GeminiConfig:
    """Resolved Gemini settings, read from the environment (Req 15.1).

    The API key is still accessible programmatically, but ``repr=False`` keeps
    the secret out of any diagnostic output (repr/str), so it can never leak
    into logs, tracebacks, or error messages (Req 14.8, 14.9).
    """

    # repr=False keeps the secret out of diagnostic output (Req 14.8, 14.9).
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: float


def load_gemini_config() -> GeminiConfig:
    """Read Gemini settings from the environment.

    Applies ``DEFAULT_MODEL`` and ``DEFAULT_TIMEOUT_SECONDS`` when the model or
    timeout variables are unset. Raises a configuration error (a provider-failure
    kind) if the API key is absent or the timeout is not a number. Never logs or
    echoes the key value (Req 15.1, 15.2, 14.8, 14.9).
    """
    api_key = os.environ.get(ENV_API_KEY)
    if not api_key:
        # Message names the ENV VAR NAME only, never a value.
        raise MissingApiKeyError(f"Environment variable {ENV_API_KEY} is not set")

    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL)

    raw_timeout = os.environ.get(ENV_TIMEOUT)
    if raw_timeout is None:
        timeout = DEFAULT_TIMEOUT_SECONDS
    else:
        try:
            timeout = float(raw_timeout)
        except ValueError:
            # An invalid timeout is surfaced as a safe provider-failure-kind
            # error, consistent with the design treating config problems as
            # provider failures. The offending raw value is NOT echoed, to
            # avoid leaking anything (Req 14.7, 14.8).
            raise ProviderFailureError(f"{ENV_TIMEOUT} must be a number") from None

    return GeminiConfig(api_key=api_key, model=model, timeout_seconds=timeout)
