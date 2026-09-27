"""Tests for the closed extraction error set (Req 14, 10.3, 15.1).

Covers existence + inheritance, programmatic distinguishability, the safe
SchemaValidationError.from_pydantic detail builder, and basic message safety.
"""

import pytest
from pydantic import BaseModel, ValidationError

from app.extraction.errors import (
    EmptyInputError,
    ExtractionError,
    MalformedResponseError,
    MissingApiKeyError,
    ProviderFailureError,
    ProviderTimeoutError,
    SchemaValidationError,
    UnexpectedResponseError,
)


# The six documented closed-set categories (Req 14.10), each mapped to a
# distinct class so a caller can tell them apart programmatically.
ALL_ERROR_TYPES = [
    EmptyInputError,
    ProviderFailureError,
    MissingApiKeyError,
    ProviderTimeoutError,
    MalformedResponseError,
    SchemaValidationError,
    UnexpectedResponseError,
]


# --- 1. Existence + inheritance ------------------------------------------


@pytest.mark.parametrize("error_type", ALL_ERROR_TYPES)
def test_every_error_is_an_extraction_error(error_type):
    """Every error type is a subclass of the single ExtractionError base (Req 14)."""
    assert issubclass(error_type, ExtractionError)
    assert issubclass(error_type, Exception)


def test_missing_api_key_is_a_provider_failure():
    """MissingApiKeyError is-a ProviderFailureError (Req 15.1) and thus ExtractionError."""
    assert issubclass(MissingApiKeyError, ProviderFailureError)
    assert issubclass(MissingApiKeyError, ExtractionError)


def test_documented_categories_are_distinct_classes():
    """The closed-set categories map to distinct classes (Req 14.10)."""
    assert len(set(ALL_ERROR_TYPES)) == len(ALL_ERROR_TYPES)


def test_catching_base_catches_all():
    """Catching ExtractionError catches every error type (Req 14.10)."""
    for error_type in ALL_ERROR_TYPES:
        with pytest.raises(ExtractionError):
            raise error_type("safe message")


def test_catching_provider_failure_catches_missing_api_key_not_timeout():
    """ProviderFailureError catches MissingApiKeyError but not ProviderTimeoutError."""
    with pytest.raises(ProviderFailureError):
        raise MissingApiKeyError("safe message")

    # A timeout is NOT a provider-failure kind, so it should slip past a
    # ProviderFailureError-only handler and be caught only by the base.
    with pytest.raises(ExtractionError) as caught:
        try:
            raise ProviderTimeoutError("safe message")
        except ProviderFailureError:  # pragma: no cover - must not match
            pytest.fail("ProviderTimeoutError must not be caught as ProviderFailureError")
    assert isinstance(caught.value, ProviderTimeoutError)


# --- 2. Distinguishability -----------------------------------------------


def test_missing_api_key_isinstance_provider_failure():
    assert isinstance(MissingApiKeyError("x"), ProviderFailureError)
    assert isinstance(MissingApiKeyError("x"), ExtractionError)


def test_timeout_is_not_a_provider_failure():
    assert not isinstance(ProviderTimeoutError("x"), ProviderFailureError)


def test_sibling_types_are_not_confused():
    """Independent categories do not share an inheritance path (Req 14.10)."""
    assert not isinstance(MalformedResponseError("x"), SchemaValidationError)
    assert not isinstance(SchemaValidationError("x"), MalformedResponseError)
    assert not isinstance(UnexpectedResponseError("x"), MalformedResponseError)
    assert not isinstance(EmptyInputError("x"), ProviderFailureError)


# --- 3. SchemaValidationError.from_pydantic ------------------------------


class _Throwaway(BaseModel):
    """Tiny local model used only to produce a real pydantic ValidationError.

    Deliberately NOT RawExtraction (that belongs to a later task).
    """

    count: int
    label: str


def _make_validation_error() -> ValidationError:
    """Trigger a ValidationError with a deliberately secret-looking value."""
    try:
        # `count` gets a non-int; `label` is the offending secret value.
        _Throwaway.model_validate({"count": "not-an-int", "label": "SECRET_API_KEY_123"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected model_validate to raise ValidationError")


def test_from_pydantic_returns_schema_validation_error():
    err = SchemaValidationError.from_pydantic(_make_validation_error())
    assert isinstance(err, SchemaValidationError)
    assert isinstance(err, ExtractionError)


def test_from_pydantic_message_mentions_schema_validation():
    err = SchemaValidationError.from_pydantic(_make_validation_error())
    assert "schema validation" in str(err)


def test_from_pydantic_message_includes_loc_and_type():
    exc = _make_validation_error()
    err = SchemaValidationError.from_pydantic(exc)
    message = str(err)
    for entry in exc.errors():
        location = ".".join(str(p) for p in entry["loc"])
        assert location in message
        assert entry["type"] in message


def test_from_pydantic_message_does_not_leak_input_values():
    """The safety check: only loc + type are surfaced, never the input value (Req 14.7, 14.8)."""
    err = SchemaValidationError.from_pydantic(_make_validation_error())
    assert "SECRET_API_KEY_123" not in str(err)
    assert "not-an-int" not in str(err)


# --- 4. Basic message safety ---------------------------------------------


@pytest.mark.parametrize(
    "error_type",
    [
        ExtractionError,
        EmptyInputError,
        ProviderFailureError,
        MissingApiKeyError,
        ProviderTimeoutError,
        MalformedResponseError,
        SchemaValidationError,
        UnexpectedResponseError,
    ],
)
def test_plain_error_stores_safe_message(error_type):
    """Constructing an error with a safe message returns it via str()."""
    err = error_type("a safe, generic message")
    assert str(err) == "a safe, generic message"
