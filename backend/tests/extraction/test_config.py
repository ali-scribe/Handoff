"""Tests for environment-based Gemini configuration (Task 4 / Req 15.1, 15.2, 14.8, 14.9)."""

import pytest

from app.extraction.config import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    ENV_API_KEY,
    ENV_MODEL,
    ENV_TIMEOUT,
    GeminiConfig,
    load_gemini_config,
)
from app.extraction.errors import MissingApiKeyError, ProviderFailureError

FAKE_KEY = "test-key-123"


def _clear_env(monkeypatch):
    """Remove all Gemini env vars so each test starts from a clean slate."""
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    monkeypatch.delenv(ENV_MODEL, raising=False)
    monkeypatch.delenv(ENV_TIMEOUT, raising=False)


@pytest.mark.parametrize("api_key_value", [None, ""])
def test_missing_or_empty_api_key_raises(monkeypatch, api_key_value):
    """An absent or empty GEMINI_API_KEY is treated as missing (Req 15.1, 14.1 edge)."""
    _clear_env(monkeypatch)
    if api_key_value is not None:
        monkeypatch.setenv(ENV_API_KEY, api_key_value)

    with pytest.raises(MissingApiKeyError) as excinfo:
        load_gemini_config()

    message = str(excinfo.value)
    # Message names the env var NAME and never echoes a value (Req 14.8).
    assert ENV_API_KEY in message
    assert FAKE_KEY not in message


def test_default_model_when_unset(monkeypatch):
    """With only the API key set, the model falls back to the default."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_API_KEY, FAKE_KEY)

    config = load_gemini_config()

    assert config.model == DEFAULT_MODEL == "gemini-2.0-flash"


def test_default_timeout_when_unset(monkeypatch):
    """With only the API key set, the timeout falls back to the default."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_API_KEY, FAKE_KEY)

    config = load_gemini_config()

    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS == 30.0


def test_env_overrides_model_and_timeout(monkeypatch):
    """Explicit env values override the defaults; timeout is parsed as a float."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(ENV_MODEL, "my-model")
    monkeypatch.setenv(ENV_TIMEOUT, "12.5")

    config = load_gemini_config()

    assert config.model == "my-model"
    assert config.timeout_seconds == 12.5
    assert isinstance(config.timeout_seconds, float)


def test_invalid_timeout_raises_provider_failure(monkeypatch):
    """A non-numeric timeout surfaces as a safe ProviderFailureError (Req 14.7, 14.8)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(ENV_TIMEOUT, "not-a-number")

    with pytest.raises(ProviderFailureError) as excinfo:
        load_gemini_config()

    message = str(excinfo.value)
    # Names the timeout env var but does NOT echo the offending raw value.
    assert ENV_TIMEOUT in message
    assert "not-a-number" not in message


def test_api_key_is_redacted_from_repr(monkeypatch):
    """The api_key value never appears in repr()/str() but stays accessible (Req 14.8, 14.9)."""
    _clear_env(monkeypatch)
    secret = "super-secret-key-xyz"
    monkeypatch.setenv(ENV_API_KEY, secret)

    config = load_gemini_config()

    assert secret not in repr(config)
    assert secret not in str(config)
    # The value is still accessible programmatically, just not shown in repr.
    assert config.api_key == secret


def test_returns_frozen_gemini_config(monkeypatch):
    """load_gemini_config returns an immutable GeminiConfig instance."""
    _clear_env(monkeypatch)
    monkeypatch.setenv(ENV_API_KEY, FAKE_KEY)

    config = load_gemini_config()

    assert isinstance(config, GeminiConfig)
    with pytest.raises(Exception):
        config.model = "changed"  # frozen dataclass rejects mutation
