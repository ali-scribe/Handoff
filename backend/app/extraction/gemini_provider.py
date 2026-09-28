"""Gemini REST provider: concrete ExtractionProvider that talks to the Gemini API via httpx."""

import json
import logging

import httpx

from app.extraction.config import GeminiConfig, load_gemini_config
from app.extraction.errors import (
    MalformedResponseError,
    ProviderFailureError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnexpectedResponseError,
)

logger = logging.getLogger(__name__)

# Gemini REST generateContent endpoint (v1beta). The model is filled in per request.
_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

# Cap on how much of a Gemini error body we log, so a large/unexpected response
# body cannot flood the logs. The body carries Gemini's own error reason (e.g.
# invalid key, quota exceeded, model not found) and never contains OUR API key,
# which is sent only as a request header.
_ERROR_BODY_LOG_LIMIT = 500


class GeminiProvider:
    """Gemini-backed ExtractionProvider (Req 11.3). Replaceable (Req 12).

    Implements the ExtractionProvider Protocol structurally (no base class).
    It calls the Gemini REST generateContent endpoint with httpx, decodes the
    model's text part, and JSON-decodes that into a dict for the service to
    validate. Every failure mode maps to a typed, secret-safe extraction error;
    the API key and raw provider text are never logged or raised (Req 14.7-14.9).
    """

    def __init__(self, config: GeminiConfig | None = None):
        # An explicitly injected config is stored as-is. When none is given, the
        # environment config is loaded LAZILY on first use (see _get_config),
        # not here — so a missing GEMINI_API_KEY does not raise during provider
        # construction (e.g. at FastAPI dependency-resolution time), but during
        # extract() within the handled request path, where the typed
        # MissingApiKeyError reaches the application error handler (Req 15.1, 15.2).
        self._config = config

    def _get_config(self) -> GeminiConfig:
        """Return the config, loading it from the environment once if needed.

        Deferred and cached: the first call with no injected config resolves
        ``load_gemini_config()`` and stores the result, so it is read only once.
        """
        if self._config is None:
            self._config = load_gemini_config()
        return self._config

    def extract(self, text: str) -> dict:
        config = self._get_config()
        prompt = _build_prompt(text)
        url = _ENDPOINT.format(model=config.model)
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            # Nudge the model toward returning strict JSON (Req 10.1 intent).
            "generationConfig": {"responseMimeType": "application/json"},
        }
        try:
            response = httpx.post(
                url,
                # Authenticate via the request HEADER, never a query param, so
                # the key cannot leak into URLs or logs (Req 14.8, 14.9).
                headers={"x-goog-api-key": config.api_key},
                json=body,
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            # TimeoutException is a subclass of HTTPError, so catch it FIRST.
            # No exception text, no URL, no key in the log or the raised error.
            logger.warning("Gemini request timed out")
            raise ProviderTimeoutError(
                "The AI provider did not respond in time"
            ) from None
        except httpx.HTTPStatusError as exc:
            # A non-2xx status from Gemini. Log the STATUS CODE and a bounded
            # snippet of the response BODY for diagnosis (e.g. invalid key,
            # quota exceeded, model not found). This is secret-safe: our API key
            # is sent as a request header and is not present in the response
            # body or status. The key/model name and full body are never logged.
            status = exc.response.status_code
            detail = exc.response.text[:_ERROR_BODY_LOG_LIMIT].replace("\n", " ")
            logger.warning("Gemini request failed: HTTP %s - %s", status, detail)
            # HTTP 503 is a transient "service unavailable" condition: the
            # request was fine but Gemini could not handle it right now. Surface
            # it as a retryable provider-unavailable error (distinct from a
            # generic provider failure) so the client can show a "try again"
            # message. The detailed status/body is already logged above; the
            # raised error carries no provider text.
            if status == 503:
                raise ProviderUnavailableError(
                    "The AI provider is temporarily unavailable"
                ) from None
            raise ProviderFailureError("The AI provider request failed") from None
        except httpx.HTTPError as exc:
            # Transport/connection-level failure with no HTTP response (DNS,
            # connection refused, TLS, etc.). Log the exception TYPE only — not
            # its message/args — to aid diagnosis without risking any leak.
            logger.warning(
                "Gemini request failed: %s", type(exc).__name__
            )
            raise ProviderFailureError("The AI provider request failed") from None

        # (1) Decode the HTTP body as JSON. A body that is not JSON at all is a
        #     malformed response (Req 14.4).
        try:
            data = response.json()
        except ValueError:
            logger.warning("Gemini returned a non-JSON body")
            raise MalformedResponseError(
                "The AI provider returned a non-JSON response"
            ) from None

        # (2) Navigate the response envelope. A missing/renamed structure is an
        #     unexpected shape (Req 14.6), distinct from a non-JSON body.
        try:
            text_out = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            logger.warning("Gemini response had an unexpected structure")
            raise UnexpectedResponseError(
                "The AI provider response had an unexpected structure"
            ) from None

        # (3) Parse the generated CONTENT text as JSON. Non-JSON content is the
        #     "malformed AI response" case (Req 14.4). Schema validity is the
        #     service's job, not the provider's (Req 10.2, 16).
        try:
            return json.loads(text_out)
        except ValueError:
            logger.warning("Gemini returned content that is not valid JSON")
            raise MalformedResponseError(
                "The AI provider returned content that is not valid JSON"
            ) from None


def _build_prompt(text: str) -> str:
    """Build the extraction instruction prompt (pure function).

    Encodes the no-invention policy and the four-condition classification
    scheme, lists all nine fields, and asks for a single strict-JSON object.
    This is best-effort guidance to the model, not a guarantee: the schema
    validation in the service and the deterministic validator downstream are
    the real safeguards (Req 4, 6, 7).
    """
    return (
        "You are an information extraction assistant for work handoffs.\n"
        "Extract ONLY information that is explicitly present in the user's "
        "text below. Do NOT invent, guess, or infer missing facts. Never "
        "invent a value for information the user did not provide.\n"
        "\n"
        "Extract these nine fields by name:\n"
        "- objective\n"
        "- owner\n"
        "- inputs\n"
        "- expected_output\n"
        "- deadline\n"
        "- acceptance_criteria\n"
        "- context\n"
        "- constraints\n"
        "- dependencies\n"
        "\n"
        "Classify EACH field with EXACTLY one condition, using one of these "
        "four string values:\n"
        '- "present": the field\'s information is clearly stated in the text.\n'
        '- "missing": the text does not supply the field\'s information. Use '
        "this whenever information is simply not provided.\n"
        '- "ambiguous": the text supplies information for the field but it is '
        "vague or open to interpretation. Preserve (keep) the extracted value "
        "and mark it ambiguous; do not replace it with a fabricated concrete "
        "value.\n"
        '- "not_applicable": use ONLY when the text gives an explicit cue that '
        "the field genuinely does not apply to this task. If information is "
        'merely absent with no such cue, use "missing" instead of '
        '"not_applicable".\n'
        "\n"
        'Set "value" to null for any field marked "missing" or '
        '"not_applicable". Keep the extracted value for a field marked '
        '"ambiguous" or "present".\n'
        "\n"
        "Return a SINGLE JSON object and NOTHING else (no prose, no markdown, "
        "no code fences). The object must have exactly the nine field keys "
        "above, each mapping to an object of the form "
        '{"value": <string | array of strings | null>, "condition": <one of '
        'the four condition strings>}, plus a "contradictions" key whose value '
        "is an array of [field_a, field_b] pairs naming two of the nine fields "
        "that clearly conflict (use an empty array when there are none).\n"
        "\n"
        "User text:\n"
        '"""\n'
        f"{text}\n"
        '"""\n'
    )