"""Closed set of typed, secret-safe extraction errors sharing one ExtractionError base."""

from pydantic import ValidationError


class ExtractionError(Exception):
    """Base for every error the extraction layer raises (Req 14)."""


class EmptyInputError(ExtractionError):
    """Input was empty or whitespace-only (Req 1.2, 1.3, 14.1)."""


class ProviderFailureError(ExtractionError):
    """The provider failed during extraction (Req 14.2)."""


class MissingApiKeyError(ProviderFailureError):
    """Required API key was not configured (Req 15.1). A provider-failure kind."""


class ProviderTimeoutError(ExtractionError):
    """The provider timed out or was unavailable (Req 14.3)."""


class MalformedResponseError(ExtractionError):
    """The provider returned a non-JSON / unparseable body (Req 14.4)."""


class SchemaValidationError(ExtractionError):
    """Raw data failed RawExtraction validation (Req 10.3, 14.5)."""

    @classmethod
    def from_pydantic(cls, exc: ValidationError) -> "SchemaValidationError":
        # Build a safe detail from Pydantic's structured errors: field
        # locations + error types only. No provider text, no secrets.
        locations = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['type']}"
            for e in exc.errors()
        )
        return cls(f"AI output failed schema validation ({locations})")


class UnexpectedResponseError(ExtractionError):
    """The provider returned a response of an unexpected shape (Req 14.6)."""
