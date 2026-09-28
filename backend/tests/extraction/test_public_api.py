"""Public API wiring tests for the ``app.extraction`` package.

These tests assert only import/identity/wiring — they do not duplicate the
behavior covered by the per-module test files. No network / Gemini calls.
"""

import app.extraction as pkg
from app.extraction import config as cfg
from app.extraction import errors, gemini_provider, provider, schema, service

# The intended public surface, exactly as declared in __init__.__all__.
EXPECTED_NAMES = {
    "ExtractionService",
    "raw_to_structured",
    "ExtractionProvider",
    "GeminiProvider",
    "RawExtraction",
    "RawField",
    "GeminiConfig",
    "load_gemini_config",
    "ExtractionError",
    "EmptyInputError",
    "ProviderFailureError",
    "MissingApiKeyError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "MalformedResponseError",
    "SchemaValidationError",
    "UnexpectedResponseError",
}


def test_single_star_style_import_of_every_public_name_succeeds():
    # A single import statement pulling every declared name must succeed.
    from app.extraction import (  # noqa: F401
        EmptyInputError,
        ExtractionError,
        ExtractionProvider,
        ExtractionService,
        GeminiConfig,
        GeminiProvider,
        MalformedResponseError,
        MissingApiKeyError,
        ProviderFailureError,
        ProviderTimeoutError,
        ProviderUnavailableError,
        RawExtraction,
        RawField,
        SchemaValidationError,
        UnexpectedResponseError,
        load_gemini_config,
        raw_to_structured,
    )


def test_reexports_are_the_same_objects_as_their_source_modules():
    # Service and pure mapping.
    assert pkg.ExtractionService is service.ExtractionService
    assert pkg.raw_to_structured is service.raw_to_structured
    # Provider protocol and concrete provider.
    assert pkg.ExtractionProvider is provider.ExtractionProvider
    assert pkg.GeminiProvider is gemini_provider.GeminiProvider
    # Schema models.
    assert pkg.RawExtraction is schema.RawExtraction
    assert pkg.RawField is schema.RawField
    # Configuration.
    assert pkg.GeminiConfig is cfg.GeminiConfig
    assert pkg.load_gemini_config is cfg.load_gemini_config
    # Error types.
    assert pkg.ExtractionError is errors.ExtractionError
    assert pkg.EmptyInputError is errors.EmptyInputError
    assert pkg.ProviderFailureError is errors.ProviderFailureError
    assert pkg.MissingApiKeyError is errors.MissingApiKeyError
    assert pkg.ProviderTimeoutError is errors.ProviderTimeoutError
    assert pkg.ProviderUnavailableError is errors.ProviderUnavailableError
    assert pkg.MalformedResponseError is errors.MalformedResponseError
    assert pkg.SchemaValidationError is errors.SchemaValidationError
    assert pkg.UnexpectedResponseError is errors.UnexpectedResponseError


def test_all_matches_expected_names_exactly_and_nothing_missing_or_extra():
    assert set(pkg.__all__) == EXPECTED_NAMES
    # No accidental duplicates in the list itself.
    assert len(pkg.__all__) == len(set(pkg.__all__))


def test_every_name_in_all_is_gettable_on_the_package():
    for name in pkg.__all__:
        assert hasattr(pkg, name), f"{name} declared in __all__ but not importable"


def test_submodule_import_paths_still_work_and_match_package_reexports():
    # Backward-compat: existing submodule import paths must still resolve and
    # be identical to the package-level re-exports.
    from app.extraction.provider import ExtractionProvider as SubProvider
    from app.extraction.service import ExtractionService as SubService

    assert SubService is pkg.ExtractionService
    assert SubProvider is pkg.ExtractionProvider
