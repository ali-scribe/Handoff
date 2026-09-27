"""Test fakes for overriding get_analysis_service in endpoint tests.

Provides:
* ``make_handoff`` — builds a StructuredHandoff with a configurable mix of
  conditions, list/None/str values, and optional contradictions.
* ``FakeExtractionService`` — a duck-typed stand-in whose ``.extract(text)``
  returns a canned StructuredHandoff or raises a supplied exception, recording
  the text it was called with.
* ``make_analysis_service`` / ``make_raising_analysis_service`` — build a REAL
  ``AnalysisService`` wired with a ``FakeExtractionService`` so the genuine
  ``validate_handoff`` runs on the canned handoff (true readiness path, no
  Gemini).

Keeping the real AnalysisService + real validate_handoff with only extraction
faked is deliberate: it exercises the true readiness logic deterministically and
offline.
"""

from app.application.analysis import AnalysisService
from app.domain import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    StructuredHandoff,
)


def _field(value, condition):
    return HandoffField(value=value, condition=condition)


def make_handoff(
    *,
    objective=None,
    owner=None,
    inputs=None,
    expected_output=None,
    deadline=None,
    acceptance_criteria=None,
    context=None,
    constraints=None,
    dependencies=None,
    contradictions=None,
) -> StructuredHandoff:
    """Build a StructuredHandoff, defaulting to an all-present (READY) handoff.

    Each keyword accepts a (value, condition) tuple to override that field. This
    mixes list values, None values, and string values across fields so the wire
    serialization is exercised end to end.
    """

    def pick(override, default_value, default_condition):
        if override is None:
            return _field(default_value, default_condition)
        value, condition = override
        return _field(value, condition)

    return StructuredHandoff(
        objective=pick(objective, "Ship the quarterly report", FieldCondition.PRESENT),
        owner=pick(owner, "Alice", FieldCondition.PRESENT),
        inputs=pick(inputs, ["data.csv", "template.docx"], FieldCondition.PRESENT),
        expected_output=pick(expected_output, "A finished PDF report", FieldCondition.PRESENT),
        deadline=pick(deadline, "2025-03-01", FieldCondition.PRESENT),
        acceptance_criteria=pick(acceptance_criteria, "Matches the template", FieldCondition.PRESENT),
        context=pick(context, "Q1 board meeting", FieldCondition.PRESENT),
        constraints=pick(constraints, None, FieldCondition.NOT_APPLICABLE),
        dependencies=pick(dependencies, ["service-x"], FieldCondition.PRESENT),
        contradictions=contradictions if contradictions is not None else [],
    )


class FakeExtractionService:
    """Duck-typed ExtractionService stand-in exposing .extract(text).

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


def make_analysis_service(handoff: StructuredHandoff) -> AnalysisService:
    """Real AnalysisService with faked extraction returning ``handoff``.

    The genuine validate_handoff runs on the canned handoff.
    """
    return AnalysisService(FakeExtractionService(handoff=handoff))


def make_raising_analysis_service(error: Exception) -> AnalysisService:
    """Real AnalysisService whose extraction raises ``error``."""
    return AnalysisService(FakeExtractionService(error=error))
