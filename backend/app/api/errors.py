"""Deterministic mapping from extraction errors to HTTP responses.

This module holds ONE small, explicit translation: a typed ExtractionError ->
(HTTP status, stable machine code, safe static human message), wrapped in the
Task-1 ``ErrorResponse``/``ApiError`` shape. There is no global/unrelated
exception infrastructure here.

Messages are FIXED and static per code — we never interpolate ``str(exc)`` into
the response, so no provider text, raw exception detail, or API key can ever
leak to the client. Pydantic request-validation (invalid request body -> 422)
is handled by FastAPI's built-in RequestValidationError and is intentionally
NOT overridden here.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.schemas import ApiError, ErrorResponse
from app.domain.answers import (
    ClarificationError,
    ContradictionNotFoundError,
    EmptyAnswerError,
    InvalidTargetFieldError,
)
from app.extraction import (
    EmptyInputError,
    ExtractionError,
    MalformedResponseError,
    MissingApiKeyError,
    ProviderFailureError,
    ProviderTimeoutError,
    SchemaValidationError,
    UnexpectedResponseError,
)

# Ordered MOST-SPECIFIC FIRST so subclasses resolve before their superclasses.
# In particular MissingApiKeyError (a ProviderFailureError subclass) must be
# matched before ProviderFailureError, and every concrete ExtractionError
# subtype must be matched before the generic ExtractionError catch-all last.
# Each entry: (exception_type, http_status, stable_code).
_ERROR_MAPPING: list[tuple[type[ExtractionError], int, str]] = [
    (EmptyInputError, 422, "empty_input"),
    (MissingApiKeyError, 500, "server_configuration_error"),
    (MalformedResponseError, 502, "malformed_ai_response"),
    (SchemaValidationError, 502, "schema_validation_failed"),
    (UnexpectedResponseError, 502, "unexpected_ai_response"),
    (ProviderTimeoutError, 504, "provider_timeout"),
    (ProviderFailureError, 502, "provider_failure"),
    (ExtractionError, 502, "extraction_error"),  # generic catch-all, LAST
]

# Fixed, safe, human-readable message per stable code. Static by design: no
# exception text is ever substituted in, so nothing sensitive can leak.
_SAFE_MESSAGES: dict[str, str] = {
    "empty_input": "The provided text was empty.",
    "server_configuration_error": "The server is not configured correctly.",
    "malformed_ai_response": "The AI provider returned a malformed response.",
    "schema_validation_failed": "The AI response did not match the expected schema.",
    "unexpected_ai_response": "The AI provider returned an unexpected response.",
    "provider_timeout": "The AI provider timed out.",
    "provider_failure": "The AI provider failed to process the request.",
    "extraction_error": "The handoff could not be analyzed.",
}


def extraction_error_to_response(exc: ExtractionError) -> tuple[int, ErrorResponse]:
    """Map a typed ExtractionError to (HTTP status, ErrorResponse).

    Walks the ordered mapping most-specific-first and returns the first match.
    The message is the fixed, safe string for the resolved code — never derived
    from ``exc`` — so no provider text or secret can leak.
    """
    for exc_type, status_code, code in _ERROR_MAPPING:
        if isinstance(exc, exc_type):
            message = _SAFE_MESSAGES[code]
            return status_code, ErrorResponse(error=ApiError(code=code, message=message))
    # Unreachable in practice: ExtractionError is the final catch-all above, and
    # this handler is only registered for ExtractionError. Kept as a defensive
    # fallback to guarantee a deterministic, safe response for any subclass.
    return 502, ErrorResponse(
        error=ApiError(code="extraction_error", message=_SAFE_MESSAGES["extraction_error"])
    )


# --- Clarification-feature error mapping --------------------------------------
#
# The clarification endpoints (apply-answers) raise the typed ClarificationError
# family from app.domain.answers. Each maps to a 422 with a stable code and a
# fixed, safe message. As with extraction errors, messages are static — never
# derived from the exception — so nothing sensitive can leak. Ordered
# most-specific-first with the generic ClarificationError last as a catch-all.
_CLARIFICATION_ERROR_MAPPING: list[tuple[type[ClarificationError], int, str]] = [
    (EmptyAnswerError, 422, "empty_answer"),
    (InvalidTargetFieldError, 422, "invalid_target_field"),
    (ContradictionNotFoundError, 422, "contradiction_not_found"),
    (ClarificationError, 422, "clarification_error"),  # generic catch-all, LAST
]

_CLARIFICATION_SAFE_MESSAGES: dict[str, str] = {
    "empty_answer": "The provided answer was empty.",
    "invalid_target_field": "The answer targeted an unknown field.",
    "contradiction_not_found": "The specified contradiction could not be found.",
    "clarification_error": "The clarification request could not be processed.",
}


def clarification_error_to_response(
    exc: ClarificationError,
) -> tuple[int, ErrorResponse]:
    """Map a typed ClarificationError to (HTTP status, ErrorResponse).

    Walks the ordered mapping most-specific-first and returns the first match.
    The message is the fixed, safe string for the resolved code — never derived
    from ``exc``.
    """
    for exc_type, status_code, code in _CLARIFICATION_ERROR_MAPPING:
        if isinstance(exc, exc_type):
            message = _CLARIFICATION_SAFE_MESSAGES[code]
            return status_code, ErrorResponse(error=ApiError(code=code, message=message))
    # Defensive fallback (ClarificationError is the final catch-all above).
    return 422, ErrorResponse(
        error=ApiError(
            code="clarification_error",
            message=_CLARIFICATION_SAFE_MESSAGES["clarification_error"],
        )
    )


def register_error_handlers(app) -> None:
    """Register the typed-error -> JSON error handlers on the app.

    Keeps all HTTP error handling in one small place: the ExtractionError handler
    (unchanged) and the ClarificationError handler. FastAPI's built-in
    RequestValidationError (invalid request body) already yields 422, so it is
    deliberately left untouched.
    """

    @app.exception_handler(ExtractionError)
    async def _handle_extraction_error(request: Request, exc: ExtractionError):
        status_code, error_response = extraction_error_to_response(exc)
        return JSONResponse(status_code=status_code, content=error_response.model_dump())

    @app.exception_handler(ClarificationError)
    async def _handle_clarification_error(request: Request, exc: ClarificationError):
        status_code, error_response = clarification_error_to_response(exc)
        return JSONResponse(status_code=status_code, content=error_response.model_dump())
