"""Tests for the Gemini provider (Task 7 / Req 11.3, 14.2-14.9, 15.1, 16).

No real Gemini/network calls happen here. The provider calls module-level
``httpx.post(...)``, so we monkeypatch ``app.extraction.gemini_provider.httpx.post``
with a fake callable that either returns a tiny fake response object or raises
the desired httpx exception. A helper captures the call kwargs so tests can
assert the URL, headers, timeout, and body the provider sent.
"""

import inspect

import httpx
import pytest

from app.extraction import gemini_provider as gp
from app.extraction.config import GeminiConfig
from app.extraction.errors import (
    MalformedResponseError,
    ProviderFailureError,
    ProviderTimeoutError,
    UnexpectedResponseError,
)
from app.extraction.gemini_provider import GeminiProvider, _build_prompt
from app.extraction.provider import ExtractionProvider

SECRET_KEY = "test-secret-key"
NINE_FIELDS = [
    "objective",
    "owner",
    "inputs",
    "expected_output",
    "deadline",
    "acceptance_criteria",
    "context",
    "constraints",
    "dependencies",
]
FOUR_CONDITIONS = ["present", "missing", "ambiguous", "not_applicable"]


def make_config(model="test-model", timeout=7.0):
    """Build an explicit config so no environment/key is needed."""
    return GeminiConfig(api_key=SECRET_KEY, model=model, timeout_seconds=timeout)


class FakeResponse:
    """Tiny stand-in for an httpx.Response exposing what the provider uses."""

    def __init__(self, json_data=None, *, raise_status=None, json_error=False):
        self._json_data = json_data
        self._raise_status = raise_status  # an exception to raise from raise_for_status
        self._json_error = json_error  # if True, .json() raises ValueError
        self.status_code = 200

    def raise_for_status(self):
        if self._raise_status is not None:
            raise self._raise_status

    def json(self):
        if self._json_error:
            raise ValueError("body is not JSON")
        return self._json_data


def envelope(text_out):
    """Build a valid Gemini response envelope wrapping the given content text."""
    return {"candidates": [{"content": {"parts": [{"text": text_out}]}}]}


@pytest.fixture
def capture_post(monkeypatch):
    """Monkeypatch httpx.post to capture kwargs and return a supplied response.

    Returns a small controller: call ``.set_response(resp)`` to control what the
    fake post returns, or ``.set_exception(exc)`` to make it raise. After a call,
    ``.kwargs`` / ``.url`` hold what the provider sent.
    """

    class Controller:
        def __init__(self):
            self.response = FakeResponse(envelope('{"objective": {"value": "x", "condition": "present"}}'))
            self.exception = None
            self.url = None
            self.kwargs = None
            self.called = False

        def set_response(self, resp):
            self.response = resp
            self.exception = None

        def set_exception(self, exc):
            self.exception = exc

        def _post(self, url, **kwargs):
            self.called = True
            self.url = url
            self.kwargs = kwargs
            if self.exception is not None:
                raise self.exception
            return self.response

    controller = Controller()
    monkeypatch.setattr(gp.httpx, "post", controller._post)
    return controller


# ---------------------------------------------------------------------------
# _build_prompt (pure function) — cases 1-4
# ---------------------------------------------------------------------------

def test_prompt_has_no_invention_instruction():
    """Case 1: the prompt tells the model not to invent facts."""
    prompt = _build_prompt("some handoff text").lower()
    assert "invent" in prompt
    # phrased as a no-invention directive
    assert "do not invent" in prompt or "never invent" in prompt


@pytest.mark.parametrize("condition", FOUR_CONDITIONS)
def test_prompt_mentions_all_four_conditions(condition):
    """Case 2: the prompt lists all four condition strings."""
    prompt = _build_prompt("x")
    assert condition in prompt


@pytest.mark.parametrize("field_name", NINE_FIELDS)
def test_prompt_mentions_all_nine_fields(field_name):
    """Case 3: the prompt names each of the nine fields."""
    prompt = _build_prompt("x")
    assert field_name in prompt


def test_prompt_requires_json_output():
    """Case 4: the prompt asks for a single JSON object only."""
    prompt = _build_prompt("x").lower()
    assert "json" in prompt


def test_prompt_includes_user_text():
    """The user's text is embedded in the prompt."""
    prompt = _build_prompt("Fix the login bug")
    assert "Fix the login bug" in prompt


# ---------------------------------------------------------------------------
# Request construction — cases 5, 6, 7
# ---------------------------------------------------------------------------

def test_provider_sends_configured_model_in_url(capture_post):
    """Case 5: the configured model appears in the generateContent URL."""
    GeminiProvider(make_config(model="test-model")).extract("hi")
    assert "test-model" in capture_post.url
    assert "generateContent" in capture_post.url


def test_provider_sends_api_key_via_header_not_url(capture_post):
    """Case 6: the key travels in the x-goog-api-key header, never the URL/params."""
    GeminiProvider(make_config()).extract("hi")
    headers = capture_post.kwargs["headers"]
    assert headers["x-goog-api-key"] == SECRET_KEY
    # The key must not leak into the URL or query params.
    assert SECRET_KEY not in capture_post.url
    assert "params" not in capture_post.kwargs or SECRET_KEY not in str(
        capture_post.kwargs.get("params")
    )


def test_provider_uses_configured_timeout(capture_post):
    """Case 7: the configured timeout is passed to httpx."""
    GeminiProvider(make_config(timeout=7.0)).extract("hi")
    assert capture_post.kwargs["timeout"] == 7.0


def test_provider_sends_prompt_in_body(capture_post):
    """The request body carries the built prompt under contents/parts/text."""
    GeminiProvider(make_config()).extract("Fix the login bug")
    body = capture_post.kwargs["json"]
    sent_text = body["contents"][0]["parts"][0]["text"]
    assert "Fix the login bug" in sent_text


# ---------------------------------------------------------------------------
# Response handling — cases 8, 9, 10
# ---------------------------------------------------------------------------

def test_valid_response_returns_parsed_dict(capture_post):
    """Case 8: a valid envelope whose content is JSON returns the parsed dict."""
    content = '{"objective": {"value": "x", "condition": "present"}}'
    capture_post.set_response(FakeResponse(envelope(content)))

    result = GeminiProvider(make_config()).extract("hi")

    assert result == {"objective": {"value": "x", "condition": "present"}}


def test_malformed_content_json_raises_malformed(capture_post):
    """Case 9: content text that is not valid JSON -> MalformedResponseError."""
    capture_post.set_response(FakeResponse(envelope("not json {{")))

    with pytest.raises(MalformedResponseError):
        GeminiProvider(make_config()).extract("hi")


@pytest.mark.parametrize("bad_envelope", [{}, {"foo": 1}, {"candidates": []}])
def test_unexpected_envelope_raises_unexpected(capture_post, bad_envelope):
    """Case 10: a missing/renamed envelope structure -> UnexpectedResponseError."""
    capture_post.set_response(FakeResponse(bad_envelope))

    with pytest.raises(UnexpectedResponseError):
        GeminiProvider(make_config()).extract("hi")


def test_non_json_body_raises_malformed(capture_post):
    """A body that is not JSON at all (.json() raises) -> MalformedResponseError."""
    capture_post.set_response(FakeResponse(json_error=True))

    with pytest.raises(MalformedResponseError):
        GeminiProvider(make_config()).extract("hi")


# ---------------------------------------------------------------------------
# Transport errors — cases 11, 12
# ---------------------------------------------------------------------------

def test_http_error_raises_provider_failure(capture_post):
    """Case 11: a generic httpx.HTTPError -> ProviderFailureError."""
    capture_post.set_exception(httpx.HTTPError("boom"))

    with pytest.raises(ProviderFailureError):
        GeminiProvider(make_config()).extract("hi")


def test_non_2xx_status_raises_provider_failure(capture_post):
    """Case 11 (variant): a non-2xx status via raise_for_status -> ProviderFailureError."""
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(500, request=request)
    status_error = httpx.HTTPStatusError(
        "server error", request=request, response=response
    )
    capture_post.set_response(FakeResponse(raise_status=status_error))

    with pytest.raises(ProviderFailureError):
        GeminiProvider(make_config()).extract("hi")


def test_timeout_raises_provider_timeout(capture_post):
    """Case 12: httpx.TimeoutException -> ProviderTimeoutError."""
    capture_post.set_exception(httpx.TimeoutException("slow"))

    with pytest.raises(ProviderTimeoutError):
        GeminiProvider(make_config()).extract("hi")


# ---------------------------------------------------------------------------
# Secret safety — case 14
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "exc",
    [httpx.TimeoutException("slow with test-secret-key"), httpx.HTTPError("fail")],
)
def test_api_key_not_leaked_in_error(capture_post, exc):
    """Case 14: raised extraction errors never contain the API key."""
    capture_post.set_exception(exc)

    with pytest.raises((ProviderTimeoutError, ProviderFailureError)) as excinfo:
        GeminiProvider(make_config()).extract("hi")

    assert SECRET_KEY not in str(excinfo.value)
    assert all(SECRET_KEY not in str(arg) for arg in excinfo.value.args)


# ---------------------------------------------------------------------------
# Boundary / structure — cases 15, 16
# ---------------------------------------------------------------------------

def test_provider_module_does_not_touch_domain_types():
    """Case 15: the provider module never references domain/service constructs."""
    src = inspect.getsource(gp)
    assert "RawExtraction" not in src
    assert "StructuredHandoff" not in src
    assert "validate_handoff" not in src


def test_provider_satisfies_extraction_provider_protocol():
    """Case 16: GeminiProvider structurally implements ExtractionProvider."""
    provider = GeminiProvider(GeminiConfig(api_key="k", model="m", timeout_seconds=1.0))
    assert isinstance(provider, ExtractionProvider)


# --- Lazy config deferral (Option A: Analyze Error-Envelope Hardening) --------


def test_construction_without_key_does_not_raise(monkeypatch):
    """Constructing GeminiProvider() with no config must NOT read the env.

    The missing-key failure is deferred to first extract(), so building the
    provider (e.g. at dependency-resolution time) never raises.
    """
    from app.extraction.config import ENV_API_KEY

    monkeypatch.delenv(ENV_API_KEY, raising=False)
    # Should not raise even though GEMINI_API_KEY is unset.
    GeminiProvider()


def test_missing_key_raises_on_first_extract(monkeypatch):
    """With no injected config and no env key, extract() raises MissingApiKeyError."""
    from app.extraction.config import ENV_API_KEY
    from app.extraction.errors import MissingApiKeyError

    monkeypatch.delenv(ENV_API_KEY, raising=False)
    provider = GeminiProvider()
    with pytest.raises(MissingApiKeyError):
        provider.extract("some text")


def test_explicit_config_is_used_and_never_loads_env(monkeypatch, capture_post):
    """An explicitly injected GeminiConfig is used as-is; env is never consulted."""
    import app.extraction.gemini_provider as module

    # If load_gemini_config were called, fail loudly.
    def _boom():
        raise AssertionError("load_gemini_config must not be called with explicit config")

    monkeypatch.setattr(module, "load_gemini_config", _boom)

    GeminiProvider(make_config(model="explicit-model")).extract("hi")
    assert "explicit-model" in capture_post.url


def test_lazy_config_is_loaded_only_once(monkeypatch, capture_post):
    """The env config is resolved once and cached across extract() calls."""
    import app.extraction.gemini_provider as module

    calls = {"n": 0}

    def _counting_load():
        calls["n"] += 1
        return make_config(model="lazy-model")

    monkeypatch.setattr(module, "load_gemini_config", _counting_load)

    provider = GeminiProvider()  # no explicit config -> lazy
    provider.extract("first")
    provider.extract("second")
    assert calls["n"] == 1
    assert "lazy-model" in capture_post.url
