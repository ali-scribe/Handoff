"""Tests for the extraction service: orchestration, conversion, errors, boundary.

Standard pytest only (no Hypothesis). These tests run the whole pipeline through
fake providers with no real AI API call (Req 13.1). They cover the design's
17-case table (Req 13.2) plus determinism (Req 13.3), the validate_handoff
idempotence composition done IN THE TEST (Req 13.4), and the hard readiness
boundary (Req 16).
"""

import inspect

import pytest

import app.extraction.service as service_module
from app.domain import (
    FieldCondition,
    HandoffFieldName,
    StructuredHandoff,
    ValidationResult,
    validate_handoff,
)
from app.extraction.errors import (
    EmptyInputError,
    MalformedResponseError,
    ProviderFailureError,
    ProviderTimeoutError,
    SchemaValidationError,
)
from app.extraction.service import ExtractionService, raw_to_structured
from tests.extraction.fakes import (
    FakeProvider,
    RaisingProvider,
    SpyProvider,
    valid_raw_payload,
)


def _service_with(payload) -> ExtractionService:
    """Build an ExtractionService backed by a FakeProvider returning ``payload``."""
    return ExtractionService(FakeProvider(payload))


# --- 1. Clear complete handoff -> values copied verbatim ------------------


def test_clear_complete_handoff_copies_values_verbatim():
    """A complete payload becomes a StructuredHandoff with values copied verbatim."""
    result = _service_with(valid_raw_payload()).extract("Fix the login bug")

    assert isinstance(result, StructuredHandoff)
    # A single-valued field.
    assert result.objective.value == "Fix the login bug"
    assert result.objective.condition == FieldCondition.PRESENT
    # A list-valued field, copied element-for-element.
    assert result.inputs.value == ["repo access", "staging creds"]
    assert result.inputs.condition == FieldCondition.PRESENT


# --- 2. Incomplete handoff -> MISSING field yields None value -------------


def test_incomplete_handoff_missing_field_is_none():
    """A field marked missing yields a HandoffField MISSING with value None."""
    payload = valid_raw_payload()
    payload["owner"] = {"value": None, "condition": "missing"}

    result = _service_with(payload).extract("Fix the login bug")

    assert result.owner.condition == FieldCondition.MISSING
    assert result.owner.value is None


# --- 3. Ambiguous handoff -> value retained, condition AMBIGUOUS ----------


def test_ambiguous_handoff_retains_value():
    """An ambiguous field keeps its value and is marked AMBIGUOUS (Req 6.1)."""
    payload = valid_raw_payload()
    payload["deadline"] = {"value": "soon", "condition": "ambiguous"}

    result = _service_with(payload).extract("Fix the login bug soon")

    assert result.deadline.condition == FieldCondition.AMBIGUOUS
    assert result.deadline.value == "soon"


# --- 4. NOT_APPLICABLE field -> None value --------------------------------


def test_not_applicable_field_is_none():
    """A not-applicable field yields NOT_APPLICABLE with value None (Req 5.2, 7.1)."""
    payload = valid_raw_payload()
    payload["owner"] = {"value": None, "condition": "not_applicable"}

    result = _service_with(payload).extract("Solo effort, no owner needed")

    assert result.owner.condition == FieldCondition.NOT_APPLICABLE
    assert result.owner.value is None


# --- 5. No-invention pass-through: output equals input, field by field ----


@pytest.mark.parametrize(
    "field_name",
    ["owner", "deadline", "inputs", "acceptance_criteria", "constraints"],
)
def test_no_invention_pass_through(field_name):
    """A MISSING/None field is passed through unchanged; the service adds nothing."""
    payload = valid_raw_payload()
    payload[field_name] = {"value": None, "condition": "missing"}

    result = _service_with(payload).extract("Fix the login bug")

    handoff_field = getattr(result, field_name)
    assert handoff_field.value is None
    assert handoff_field.condition == FieldCondition.MISSING


# --- 6. Malformed provider output (non-dict) -> MalformedResponseError -----


@pytest.mark.parametrize(
    "bad_output",
    [
        ["not", "a", "dict"],
        "a bare string",
        42,
        None,
    ],
)
def test_non_dict_output_raises_malformed(bad_output):
    """A provider returning a non-dict body raises MalformedResponseError (Req 14.4)."""
    with pytest.raises(MalformedResponseError):
        _service_with(bad_output).extract("Fix the login bug")


# --- 7. Invalid enum/condition -> SchemaValidationError -------------------


def test_invalid_condition_raises_schema_validation():
    """A bad condition string surfaces as SchemaValidationError (Req 3.2, 10.3)."""
    payload = valid_raw_payload()
    payload["objective"] = {"value": "Fix it", "condition": "urgent"}

    with pytest.raises(SchemaValidationError):
        _service_with(payload).extract("Fix the login bug")


# --- 8. Invalid contradiction field name -> SchemaValidationError ---------


def test_invalid_contradiction_name_raises_schema_validation():
    """A contradiction naming a non-field surfaces as SchemaValidationError (Req 9.4)."""
    payload = valid_raw_payload()
    payload["contradictions"] = [["objective", "banana"]]

    with pytest.raises(SchemaValidationError):
        _service_with(payload).extract("Fix the login bug")


# --- 9. Provider failure propagates ---------------------------------------


def test_provider_failure_propagates():
    """A ProviderFailureError from the provider propagates unchanged (Req 14.2)."""
    service = ExtractionService(RaisingProvider(ProviderFailureError("boom")))

    with pytest.raises(ProviderFailureError):
        service.extract("Fix the login bug")


# --- 10. Provider timeout propagates --------------------------------------


def test_provider_timeout_propagates():
    """A ProviderTimeoutError from the provider propagates unchanged (Req 14.3)."""
    service = ExtractionService(RaisingProvider(ProviderTimeoutError("slow")))

    with pytest.raises(ProviderTimeoutError):
        service.extract("Fix the login bug")


# --- 11. Empty input -> EmptyInputError, provider NOT called --------------


@pytest.mark.parametrize("text", ["", "   ", "\t\n  "])
def test_empty_or_whitespace_input_raises_and_skips_provider(text):
    """Empty/whitespace input raises EmptyInputError before the provider is called."""
    spy = SpyProvider(valid_raw_payload())
    service = ExtractionService(spy)

    with pytest.raises(EmptyInputError):
        service.extract(text)

    assert spy.called is False
    assert spy.calls == []


def test_none_input_raises_empty_input_error():
    """A None input is guarded and raises EmptyInputError, provider not called."""
    spy = SpyProvider(valid_raw_payload())
    service = ExtractionService(spy)

    with pytest.raises(EmptyInputError):
        service.extract(None)

    assert spy.called is False


# --- 12. Successful conversion returns a StructuredHandoff ----------------


def test_successful_conversion_returns_structured_handoff():
    """A valid payload yields a StructuredHandoff instance (Req 8.1)."""
    result = _service_with(valid_raw_payload()).extract("Fix the login bug")

    assert isinstance(result, StructuredHandoff)


# --- 13. Declared-contradiction conversion, unchanged and in order --------


def test_declared_contradiction_passes_through_unchanged():
    """A declared contradiction pair is preserved in order (Req 9.1)."""
    payload = valid_raw_payload()
    payload["contradictions"] = [["deadline", "constraints"]]

    result = _service_with(payload).extract("Fix the login bug")

    assert result.contradictions == [
        (HandoffFieldName.DEADLINE, HandoffFieldName.CONSTRAINTS)
    ]


# --- 14. Determinism: same payload twice -> equal StructuredHandoff -------


def test_determinism_same_payload_yields_equal_handoffs():
    """Extracting the same payload twice yields equal StructuredHandoffs (Req 13.3)."""
    service = _service_with(valid_raw_payload())

    first = service.extract("Fix the login bug")
    second = service.extract("Fix the login bug")

    assert first == second


# --- 15. validate_handoff idempotence composed IN THE TEST ----------------


def test_validate_handoff_idempotent_composed_in_test():
    """Composing validate_handoff (in the test) twice yields equal results (Req 13.4).

    The service itself never calls validate_handoff — the composition happens
    here, at the boundary, to prove it works while the service stays
    readiness-free (Req 16).
    """
    handoff = _service_with(valid_raw_payload()).extract("Fix the login bug")

    first = validate_handoff(handoff)
    second = validate_handoff(handoff)

    assert isinstance(first, ValidationResult)
    assert first == second


# --- 16. Boundary enforcement --------------------------------------------


def test_extract_return_type_is_structured_handoff():
    """A produced instance is a StructuredHandoff (runtime boundary check) (Req 16.3)."""
    result = _service_with(valid_raw_payload()).extract("Fix the login bug")

    assert type(result) is StructuredHandoff


def test_service_module_does_not_reference_readiness():
    """The service source references no readiness machinery (Req 16.1, 16.2)."""
    src = inspect.getsource(service_module)

    assert "validate_handoff" not in src
    assert "ReadinessState" not in src
    assert "ValidationResult" not in src


# --- 17. Extra-key rejection ----------------------------------------------


def test_surprise_top_level_key_raises_schema_validation():
    """A surprise top-level key surfaces as SchemaValidationError (extra='forbid')."""
    payload = valid_raw_payload()
    payload["readiness"] = "ready"

    with pytest.raises(SchemaValidationError):
        _service_with(payload).extract("Fix the login bug")


# --- Bonus: raw_to_structured is a usable pure mapping --------------------


def test_raw_to_structured_pure_mapping():
    """raw_to_structured builds a StructuredHandoff directly from validated raw data."""
    from app.extraction.schema import RawExtraction

    raw = RawExtraction.model_validate(valid_raw_payload())
    result = raw_to_structured(raw)

    assert isinstance(result, StructuredHandoff)
    assert result.objective.value == "Fix the login bug"
