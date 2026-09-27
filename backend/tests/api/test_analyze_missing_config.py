"""Regression: /api/handoff/analyze returns the typed error envelope when the
Gemini configuration is missing.

Before the Option A fix, a missing GEMINI_API_KEY raised MissingApiKeyError during
GeminiProvider construction at FastAPI dependency-resolution time, bypassing the
application-level ExtractionError handler and producing a raw, empty-body HTTP 500.

These tests exercise the REAL get_analysis_service dependency (NO override) with
GEMINI_API_KEY absent, so the failure now surfaces inside extract() within the
handled request path and is mapped to the standard envelope. No real Gemini/network
call happens — construction fails at config load, before any HTTP request.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_analysis_service
from app.extraction.config import ENV_API_KEY, ENV_MODEL, ENV_TIMEOUT

ANALYZE_URL = "/api/handoff/analyze"


@pytest.fixture
def real_dependency_client(monkeypatch):
    """A TestClient that uses the REAL get_analysis_service with no Gemini env.

    Ensures no analyze dependency override is installed (so the production
    factory runs) and that the Gemini environment variables are unset.
    """
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    monkeypatch.delenv(ENV_MODEL, raising=False)
    monkeypatch.delenv(ENV_TIMEOUT, raising=False)
    # Make sure no other test's override leaks into this one.
    app.dependency_overrides.pop(get_analysis_service, None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_missing_config_returns_http_500(real_dependency_client):
    response = real_dependency_client.post(ANALYZE_URL, json={"text": "fix the bug"})
    assert response.status_code == 500


def test_missing_config_returns_standard_error_envelope(real_dependency_client):
    response = real_dependency_client.post(ANALYZE_URL, json={"text": "fix the bug"})
    body = response.json()
    # Non-empty body with the standard {error: {code, message}} envelope.
    assert "error" in body
    assert set(body["error"].keys()) == {"code", "message"}


def test_missing_config_exact_code(real_dependency_client):
    response = real_dependency_client.post(ANALYZE_URL, json={"text": "fix the bug"})
    assert response.json()["error"]["code"] == "server_configuration_error"


def test_missing_config_exact_safe_message(real_dependency_client):
    response = real_dependency_client.post(ANALYZE_URL, json={"text": "fix the bug"})
    assert (
        response.json()["error"]["message"]
        == "The server is not configured correctly."
    )


def test_missing_config_does_not_leak_internals(real_dependency_client):
    response = real_dependency_client.post(ANALYZE_URL, json={"text": "fix the bug"})
    text = response.text
    # No env var names, config internals, or stack traces in the response.
    assert ENV_API_KEY not in text
    assert "Traceback" not in text
    assert "load_gemini_config" not in text
    assert "GeminiConfig" not in text
