"""AI handoff extraction package: turns free-form text into a StructuredHandoff.

This module re-exports the public surface of the extraction layer so callers can
import from ``app.extraction`` directly instead of reaching into submodules.
"""

from app.extraction.config import GeminiConfig, load_gemini_config
from app.extraction.errors import (
    EmptyInputError,
    ExtractionError,
    MalformedResponseError,
    MissingApiKeyError,
    ProviderFailureError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SchemaValidationError,
    UnexpectedResponseError,
)
from app.extraction.gemini_provider import GeminiProvider
from app.extraction.provider import ExtractionProvider
from app.extraction.schema import RawExtraction, RawField
from app.extraction.service import ExtractionService, raw_to_structured

__all__ = [
    # Service and pure mapping
    "ExtractionService",
    "raw_to_structured",
    # Provider protocol and concrete provider
    "ExtractionProvider",
    "GeminiProvider",
    # AI output schema models
    "RawExtraction",
    "RawField",
    # Configuration
    "GeminiConfig",
    "load_gemini_config",
    # Error types
    "ExtractionError",
    "EmptyInputError",
    "ProviderFailureError",
    "MissingApiKeyError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "MalformedResponseError",
    "SchemaValidationError",
    "UnexpectedResponseError",
]
