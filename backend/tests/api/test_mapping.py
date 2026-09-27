"""Tests for the pure domain -> API DTO mapping layer (app.api.mapping).

These tests exercise translation only: every mapped attribute must equal its
source, values (including None and lists) are copied verbatim, contradiction
pair order is preserved, issues keep their order, and the inputs are never
mutated. No business logic (readiness/severity) is asserted here beyond what a
real ValidationResult already carries.
"""

import pytest

from app.domain import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    Issue,
    IssueSeverity,
    IssueType,
    ReadinessState,
    StructuredHandoff,
    ValidationResult,
    validate_handoff,
)
from app.api.schemas import (
    AnalyzeResponse,
    HandoffFieldOut,
    IssueOut,
    StructuredHandoffOut,
    ValidationResultOut,
)
from app.api.mapping import (
    handoff_field_to_out,
    structured_handoff_to_out,
    issue_to_out,
    validation_result_to_out,
    to_analyze_response,
)


# --- Helpers ----------------------------------------------------------------

# The nine field names in domain order, matching StructuredHandoff attributes.
FIELD_NAMES = [
    "objective",
    "owner",
    "inputs",
    "expected_output",
    "deadline",
    "acceptance_criteria",
    "context",
    "constraints",
    "dependencies",
]


def make_handoff(
    *,
    contradictions=None,
) -> StructuredHandoff:
    """Build a StructuredHandoff with a mix of conditions and value shapes."""
    return StructuredHandoff(
        objective=HandoffField(value="Ship the report", condition=FieldCondition.PRESENT),
        owner=HandoffField(value=None, condition=FieldCondition.MISSING),
        inputs=HandoffField(value=["a", "b"], condition=FieldCondition.PRESENT),
        expected_output=HandoffField(value="A PDF", condition=FieldCondition.PRESENT),
        deadline=HandoffField(value="soon", condition=FieldCondition.AMBIGUOUS),
        acceptance_criteria=HandoffField(value=None, condition=FieldCondition.NOT_APPLICABLE),
        context=HandoffField(value="Q3 planning", condition=FieldCondition.PRESENT),
        constraints=HandoffField(value=None, condition=FieldCondition.MISSING),
        dependencies=HandoffField(value=["svc-x"], condition=FieldCondition.PRESENT),
        contradictions=contradictions if contradictions is not None else [],
    )


# --- handoff_field_to_out ---------------------------------------------------


@pytest.mark.parametrize("condition", list(FieldCondition))
def test_handoff_field_to_out_preserves_every_condition(condition):
    field = HandoffField(value="x", condition=condition)
    out = handoff_field_to_out(field)
    assert isinstance(out, HandoffFieldOut)
    assert out.condition == condition
    assert out.value == "x"


def test_handoff_field_to_out_preserves_string_value():
    out = handoff_field_to_out(
        HandoffField(value="hello", condition=FieldCondition.PRESENT)
    )
    assert out.value == "hello"


def test_handoff_field_to_out_preserves_list_value():
    out = handoff_field_to_out(
        HandoffField(value=["a", "b"], condition=FieldCondition.PRESENT)
    )
    assert out.value == ["a", "b"]


def test_handoff_field_to_out_preserves_none_value():
    out = handoff_field_to_out(
        HandoffField(value=None, condition=FieldCondition.MISSING)
    )
    assert out.value is None
    assert out.condition == FieldCondition.MISSING


# --- structured_handoff_to_out ----------------------------------------------


def test_structured_handoff_to_out_maps_all_nine_fields():
    handoff = make_handoff()
    out = structured_handoff_to_out(handoff)
    assert isinstance(out, StructuredHandoffOut)
    for name in FIELD_NAMES:
        domain_field = getattr(handoff, name)
        out_field = getattr(out, name)
        assert isinstance(out_field, HandoffFieldOut)
        assert out_field.value == domain_field.value
        assert out_field.condition == domain_field.condition


def test_structured_handoff_to_out_preserves_contradiction_order():
    contradictions = [
        (HandoffFieldName.DEADLINE, HandoffFieldName.DEPENDENCIES),
        (HandoffFieldName.OBJECTIVE, HandoffFieldName.OWNER),
    ]
    handoff = make_handoff(contradictions=contradictions)
    out = structured_handoff_to_out(handoff)
    assert out.contradictions == [
        (HandoffFieldName.DEADLINE, HandoffFieldName.DEPENDENCIES),
        (HandoffFieldName.OBJECTIVE, HandoffFieldName.OWNER),
    ]


def test_structured_handoff_to_out_empty_contradictions():
    out = structured_handoff_to_out(make_handoff())
    assert out.contradictions == []


# --- issue_to_out -----------------------------------------------------------


def test_issue_to_out_without_secondary_field():
    issue = Issue(
        issue_type=IssueType.MISSING_OBJECTIVE,
        severity=IssueSeverity.CRITICAL,
        field=HandoffFieldName.OBJECTIVE,
        explanation="No objective provided.",
    )
    out = issue_to_out(issue)
    assert isinstance(out, IssueOut)
    assert out.issue_type == IssueType.MISSING_OBJECTIVE
    assert out.severity == IssueSeverity.CRITICAL
    assert out.field == HandoffFieldName.OBJECTIVE
    assert out.secondary_field is None
    assert out.explanation == "No objective provided."


def test_issue_to_out_with_secondary_field():
    issue = Issue(
        issue_type=IssueType.CONTRADICTORY_INFORMATION,
        severity=IssueSeverity.IMPORTANT,
        field=HandoffFieldName.DEADLINE,
        secondary_field=HandoffFieldName.DEPENDENCIES,
        explanation="Deadline conflicts with dependencies.",
    )
    out = issue_to_out(issue)
    assert out.issue_type == IssueType.CONTRADICTORY_INFORMATION
    assert out.severity == IssueSeverity.IMPORTANT
    assert out.field == HandoffFieldName.DEADLINE
    assert out.secondary_field == HandoffFieldName.DEPENDENCIES
    assert out.explanation == "Deadline conflicts with dependencies."


# --- validation_result_to_out -----------------------------------------------


@pytest.mark.parametrize("readiness", list(ReadinessState))
def test_validation_result_to_out_preserves_readiness(readiness):
    result = ValidationResult(readiness_state=readiness, issues=[])
    out = validation_result_to_out(result)
    assert isinstance(out, ValidationResultOut)
    assert out.readiness_state == readiness
    assert out.issues == []


def test_validation_result_to_out_maps_issues_in_order():
    issues = [
        Issue(
            issue_type=IssueType.MISSING_OBJECTIVE,
            severity=IssueSeverity.CRITICAL,
            field=HandoffFieldName.OBJECTIVE,
            explanation="first",
        ),
        Issue(
            issue_type=IssueType.VAGUE_DEADLINE,
            severity=IssueSeverity.MINOR,
            field=HandoffFieldName.DEADLINE,
            explanation="second",
        ),
        Issue(
            issue_type=IssueType.CONTRADICTORY_INFORMATION,
            severity=IssueSeverity.IMPORTANT,
            field=HandoffFieldName.DEADLINE,
            secondary_field=HandoffFieldName.DEPENDENCIES,
            explanation="third",
        ),
    ]
    result = ValidationResult(
        readiness_state=ReadinessState.NOT_READY, issues=issues
    )
    out = validation_result_to_out(result)
    assert len(out.issues) == 3
    assert [i.explanation for i in out.issues] == ["first", "second", "third"]
    for src, mapped in zip(issues, out.issues):
        assert mapped.issue_type == src.issue_type
        assert mapped.severity == src.severity
        assert mapped.field == src.field
        assert mapped.secondary_field == src.secondary_field
        assert mapped.explanation == src.explanation


# --- to_analyze_response (combined, with the REAL validator) -----------------


def test_to_analyze_response_with_real_validation():
    handoff = make_handoff()
    result = validate_handoff(handoff)  # genuine ValidationResult
    response = to_analyze_response(handoff, result)

    assert isinstance(response, AnalyzeResponse)
    # handoff maps correctly across all nine fields
    for name in FIELD_NAMES:
        domain_field = getattr(handoff, name)
        out_field = getattr(response.handoff, name)
        assert out_field.value == domain_field.value
        assert out_field.condition == domain_field.condition
    # validation is passed through faithfully
    assert response.validation.readiness_state == result.readiness_state
    assert len(response.validation.issues) == len(result.issues)


# --- Non-mutation -----------------------------------------------------------


def test_mapping_does_not_mutate_inputs():
    contradictions = [(HandoffFieldName.OBJECTIVE, HandoffFieldName.OWNER)]
    handoff = make_handoff(contradictions=contradictions)
    result = validate_handoff(handoff)

    original_objective_value = handoff.objective.value
    original_contradictions = list(handoff.contradictions)
    original_readiness = result.readiness_state
    original_issue_count = len(result.issues)

    to_analyze_response(handoff, result)

    # Domain models are frozen; assert key attributes still equal originals to
    # document the intent that mapping is read-only.
    assert handoff.objective.value == original_objective_value
    assert list(handoff.contradictions) == original_contradictions
    assert result.readiness_state == original_readiness
    assert len(result.issues) == original_issue_count


# --- Determinism ------------------------------------------------------------


def test_mapping_is_deterministic():
    handoff = make_handoff(
        contradictions=[(HandoffFieldName.DEADLINE, HandoffFieldName.DEPENDENCIES)]
    )
    result = validate_handoff(handoff)
    assert to_analyze_response(handoff, result) == to_analyze_response(handoff, result)
    assert structured_handoff_to_out(handoff) == structured_handoff_to_out(handoff)
    assert validation_result_to_out(result) == validation_result_to_out(result)
