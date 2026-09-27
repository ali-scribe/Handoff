"""Tests for the application-layer AnalysisService (composition only).

These verify that AnalysisService faithfully composes extraction with the real
``validate_handoff`` and adds no logic of its own: it returns whatever readiness
the validator decides, passes the exact text to extraction, and lets typed
ExtractionErrors propagate unchanged (it never catches them).
"""

import pytest

from app.application.analysis import AnalysisService
from app.domain import (
    FieldCondition,
    HandoffField,
    ReadinessState,
    StructuredHandoff,
    ValidationResult,
    validate_handoff,
)
from app.extraction import EmptyInputError, ProviderFailureError


# --- Fakes ------------------------------------------------------------------


class FakeExtractionService:
    """Duck-typed stand-in exposing .extract(text).

    Returns a canned StructuredHandoff, or raises a supplied exception. Records
    the text it was last called with so tests can assert delegation.
    """

    def __init__(self, *, handoff=None, error=None):
        self._handoff = handoff
        self._error = error
        self.received_text = None

    def extract(self, text: str) -> StructuredHandoff:
        self.received_text = text
        if self._error is not None:
            raise self._error
        return self._handoff


# --- Helpers ----------------------------------------------------------------


def _field(value, condition):
    return HandoffField(value=value, condition=condition)


def make_ready_handoff() -> StructuredHandoff:
    """All required fields present -> validator yields READY."""
    return StructuredHandoff(
        objective=_field("Ship the report", FieldCondition.PRESENT),
        owner=_field("Alice", FieldCondition.PRESENT),
        inputs=_field(["data.csv"], FieldCondition.PRESENT),
        expected_output=_field("A PDF", FieldCondition.PRESENT),
        deadline=_field("2025-01-01", FieldCondition.PRESENT),
        acceptance_criteria=_field("Looks good", FieldCondition.PRESENT),
        context=_field("Q3", FieldCondition.PRESENT),
        constraints=_field(None, FieldCondition.NOT_APPLICABLE),
        dependencies=_field(["svc-x"], FieldCondition.PRESENT),
    )


def make_not_ready_handoff() -> StructuredHandoff:
    """Objective missing -> CRITICAL issue -> validator yields NOT_READY."""
    handoff = make_ready_handoff()
    return handoff.model_copy(
        update={"objective": _field(None, FieldCondition.MISSING)}
    )


# --- Tests ------------------------------------------------------------------


def test_analyze_returns_structured_handoff_and_validation_result():
    handoff = make_ready_handoff()
    service = AnalysisService(FakeExtractionService(handoff=handoff))

    returned_handoff, result = service.analyze("some text")

    assert isinstance(returned_handoff, StructuredHandoff)
    assert isinstance(result, ValidationResult)


def test_analyze_returns_validation_equal_to_validate_handoff():
    handoff = make_ready_handoff()
    service = AnalysisService(FakeExtractionService(handoff=handoff))

    returned_handoff, result = service.analyze("text")

    # The service must not recompute or alter readiness; it returns exactly what
    # validate_handoff decides for the same handoff.
    assert returned_handoff == handoff
    assert result == validate_handoff(handoff)


def test_analyze_faithfully_returns_ready_verdict():
    handoff = make_ready_handoff()
    service = AnalysisService(FakeExtractionService(handoff=handoff))
    _, result = service.analyze("text")
    assert result.readiness_state == ReadinessState.READY


def test_analyze_faithfully_returns_not_ready_verdict():
    handoff = make_not_ready_handoff()
    service = AnalysisService(FakeExtractionService(handoff=handoff))
    _, result = service.analyze("text")
    assert result.readiness_state == ReadinessState.NOT_READY


def test_analyze_passes_exact_text_to_extraction():
    fake = FakeExtractionService(handoff=make_ready_handoff())
    service = AnalysisService(fake)
    service.analyze("the precise input text")
    assert fake.received_text == "the precise input text"


def test_analyze_propagates_empty_input_error():
    service = AnalysisService(
        FakeExtractionService(error=EmptyInputError("empty"))
    )
    with pytest.raises(EmptyInputError):
        service.analyze("")


def test_analyze_propagates_provider_failure_error():
    service = AnalysisService(
        FakeExtractionService(error=ProviderFailureError("boom"))
    )
    with pytest.raises(ProviderFailureError):
        service.analyze("text")
