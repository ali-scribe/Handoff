"""Unit tests for the extraction-error -> HTTP-response mapping (app.api.errors).

Assert the exact (status, code) pair for every mapped error type, that each
message is a non-empty safe string, that the subclass-ordering bug is guarded
(MissingApiKeyError resolves to 500, NOT 502 provider_failure), and that no
secret carried in an exception's args leaks into the response message.
"""

import pytest

from app.api.errors import extraction_error_to_response
from app.api.schemas import ErrorResponse
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


# (exception, expected_status, expected_code)
CASES = [
    (EmptyInputError("x"), 422, "empty_input"),
    (MissingApiKeyError("x"), 500, "server_configuration_error"),
    (MalformedResponseError("x"), 502, "malformed_ai_response"),
    (SchemaValidationError("x"), 502, "schema_validation_failed"),
    (UnexpectedResponseError("x"), 502, "unexpected_ai_response"),
    (ProviderTimeoutError("x"), 504, "provider_timeout"),
    (ProviderFailureError("x"), 502, "provider_failure"),
    (ExtractionError("x"), 502, "extraction_error"),
]


@pytest.mark.parametrize("exc,expected_status,expected_code", CASES)
def test_maps_each_error_type(exc, expected_status, expected_code):
    status_code, response = extraction_error_to_response(exc)
    assert status_code == expected_status
    assert isinstance(response, ErrorResponse)
    assert response.error.code == expected_code
    assert isinstance(response.error.message, str)
    assert response.error.message.strip() != ""


def test_missing_api_key_resolves_to_500_not_502():
    # Guards the subclass-ordering bug: MissingApiKeyError is a
    # ProviderFailureError subclass, so it must be matched first (500), never
    # shadowed by ProviderFailureError (502).
    status_code, response = extraction_error_to_response(MissingApiKeyError("x"))
    assert status_code == 500
    assert response.error.code == "server_configuration_error"
    assert status_code != 502
    assert response.error.code != "provider_failure"


def test_generic_extraction_error_is_catch_all():
    status_code, response = extraction_error_to_response(ExtractionError("x"))
    assert status_code == 502
    assert response.error.code == "extraction_error"


def test_missing_api_key_does_not_leak_secret_in_message():
    secret = "SUPER_SECRET_API_KEY_abc123"
    _, response = extraction_error_to_response(MissingApiKeyError(secret))
    assert secret not in response.error.message
    assert response.error.message == "The server is not configured correctly."


def test_schema_validation_error_does_not_leak_exception_text():
    leaky = "leaked-provider-detail-xyz"
    _, response = extraction_error_to_response(SchemaValidationError(leaky))
    assert leaky not in response.error.message
