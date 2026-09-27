"""Focused tests for the API-owned request/response models in app.api.schemas.

These operate on the Pydantic models directly (no endpoint exists yet). They
cover valid construction, round-tripping, reuse of the domain enums, and
rejection of malformed data (bad enum values, extra keys via extra="forbid").
"""

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ApiError,
    ErrorResponse,
    HandoffFieldOut,
    IssueOut,
    StructuredHandoffOut,
    ValidationResultOut,
)
from app.domain import (
    FieldCondition,
    HandoffFieldName,
    IssueSeverity,
    IssueType,
    ReadinessState,
)


# --------------------------------------------------------------------------- #
# AnalyzeRequest
# --------------------------------------------------------------------------- #
def test_analyze_request_valid_preserves_text():
    req = AnalyzeRequest(text="Fix the login bug")
    assert req.text == "Fix the login bug"


def test_analyze_request_missing_text_raises():
    with pytest.raises(ValidationError):
        AnalyzeRequest()


def test_analyze_request_wrong_text_type_raises():
    with pytest.raises(ValidationError):
        AnalyzeRequest(text=123)


def test_analyze_request_extra_key_rejected():
    with pytest.raises(ValidationError):
        AnalyzeRequest(text="hi", unexpected="nope")


# --------------------------------------------------------------------------- #
# HandoffFieldOut
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "condition",
    ["present", "missing", "ambiguous", "not_applicable"],
)
def test_handoff_field_out_all_conditions(condition):
    field = HandoffFieldOut(value="something", condition=condition)
    assert field.condition == FieldCondition(condition)


def test_handoff_field_out_list_value():
    field = HandoffFieldOut(value=["a", "b"], condition="present")
    assert field.value == ["a", "b"]


@pytest.mark.parametrize("condition", ["missing", "not_applicable"])
def test_handoff_field_out_null_value_preserved(condition):
    field = HandoffFieldOut(value=None, condition=condition)
    assert field.value is None
    assert field.condition == FieldCondition(condition)


def test_handoff_field_out_invalid_condition_raises():
    with pytest.raises(ValidationError):
        HandoffFieldOut(value="x", condition="urgent")


def test_handoff_field_out_extra_key_rejected():
    with pytest.raises(ValidationError):
        HandoffFieldOut(value="x", condition="present", note="extra")


# --------------------------------------------------------------------------- #
# StructuredHandoffOut
# --------------------------------------------------------------------------- #
def _make_structured_handoff(contradictions=None):
    return StructuredHandoffOut(
        objective=HandoffFieldOut(value="Ship the feature", condition="present"),
        owner=HandoffFieldOut(value=None, condition="missing"),
        inputs=HandoffFieldOut(value=["spec.md", "designs.fig"], condition="present"),
        expected_output=HandoffFieldOut(value="A deployed API", condition="present"),
        deadline=HandoffFieldOut(value=None, condition="missing"),
        acceptance_criteria=HandoffFieldOut(value=None, condition="not_applicable"),
        context=HandoffFieldOut(value="Q3 roadmap", condition="present"),
        constraints=HandoffFieldOut(value=None, condition="not_applicable"),
        dependencies=HandoffFieldOut(value="Auth service", condition="ambiguous"),
        contradictions=contradictions if contradictions is not None else [],
    )


def test_structured_handoff_out_valid_round_trip():
    handoff = _make_structured_handoff()
    dumped = handoff.model_dump()
    assert dumped["objective"]["value"] == "Ship the feature"
    assert dumped["objective"]["condition"] == "present"
    assert dumped["owner"]["value"] is None
    assert dumped["inputs"]["value"] == ["spec.md", "designs.fig"]
    assert dumped["contradictions"] == []


def test_structured_handoff_out_preserves_contradiction_pair():
    handoff = _make_structured_handoff(contradictions=[("deadline", "dependencies")])
    assert handoff.contradictions == [
        (HandoffFieldName.DEADLINE, HandoffFieldName.DEPENDENCIES)
    ]


def test_structured_handoff_out_accepts_enum_member_contradictions():
    handoff = _make_structured_handoff(
        contradictions=[(HandoffFieldName.OBJECTIVE, HandoffFieldName.OWNER)]
    )
    assert handoff.contradictions == [
        (HandoffFieldName.OBJECTIVE, HandoffFieldName.OWNER)
    ]


def test_structured_handoff_out_invalid_contradiction_name_raises():
    with pytest.raises(ValidationError):
        _make_structured_handoff(contradictions=[("banana", "dependencies")])


def test_structured_handoff_out_extra_key_rejected():
    with pytest.raises(ValidationError):
        StructuredHandoffOut(
            objective=HandoffFieldOut(value="x", condition="present"),
            owner=HandoffFieldOut(value=None, condition="missing"),
            inputs=HandoffFieldOut(value=None, condition="missing"),
            expected_output=HandoffFieldOut(value=None, condition="missing"),
            deadline=HandoffFieldOut(value=None, condition="missing"),
            acceptance_criteria=HandoffFieldOut(value=None, condition="missing"),
            context=HandoffFieldOut(value=None, condition="missing"),
            constraints=HandoffFieldOut(value=None, condition="missing"),
            dependencies=HandoffFieldOut(value=None, condition="missing"),
            surprise="nope",
        )


# --------------------------------------------------------------------------- #
# IssueOut
# --------------------------------------------------------------------------- #
def test_issue_out_valid_preserves_fields():
    issue = IssueOut(
        issue_type="missing_objective",
        severity="critical",
        field="objective",
        explanation="No objective was provided.",
    )
    assert issue.issue_type == IssueType.MISSING_OBJECTIVE
    assert issue.severity == IssueSeverity.CRITICAL
    assert issue.field == HandoffFieldName.OBJECTIVE
    assert issue.secondary_field is None
    assert issue.explanation == "No objective was provided."


def test_issue_out_with_secondary_field():
    issue = IssueOut(
        issue_type="contradictory_information",
        severity="important",
        field="deadline",
        secondary_field="dependencies",
        explanation="Deadline conflicts with dependency availability.",
    )
    assert issue.field == HandoffFieldName.DEADLINE
    assert issue.secondary_field == HandoffFieldName.DEPENDENCIES


@pytest.mark.parametrize("severity", ["critical", "important", "minor"])
def test_issue_out_all_severities(severity):
    issue = IssueOut(
        issue_type="vague_objective",
        severity=severity,
        field="objective",
        explanation="x",
    )
    assert issue.severity == IssueSeverity(severity)


@pytest.mark.parametrize(
    "issue_type",
    [
        "missing_objective",
        "vague_objective",
        "missing_required_input",
        "missing_expected_output",
        "vague_deadline",
        "missing_acceptance_criteria",
        "unresolved_dependency",
        "contradictory_information",
        "ambiguous_ownership",
        "vague_action_language",
    ],
)
def test_issue_out_all_issue_types(issue_type):
    issue = IssueOut(
        issue_type=issue_type,
        severity="minor",
        field="objective",
        explanation="x",
    )
    assert issue.issue_type == IssueType(issue_type)


def test_issue_out_invalid_severity_raises():
    with pytest.raises(ValidationError):
        IssueOut(
            issue_type="missing_objective",
            severity="blocker",
            field="objective",
            explanation="x",
        )


def test_issue_out_invalid_issue_type_raises():
    with pytest.raises(ValidationError):
        IssueOut(
            issue_type="not_a_real_type",
            severity="minor",
            field="objective",
            explanation="x",
        )


def test_issue_out_extra_key_rejected():
    with pytest.raises(ValidationError):
        IssueOut(
            issue_type="missing_objective",
            severity="minor",
            field="objective",
            explanation="x",
            hint="nope",
        )


# --------------------------------------------------------------------------- #
# ValidationResultOut
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "readiness_state",
    ["ready", "needs_clarification", "not_ready"],
)
def test_validation_result_out_all_readiness_states(readiness_state):
    result = ValidationResultOut(readiness_state=readiness_state)
    assert result.readiness_state == ReadinessState(readiness_state)
    assert result.issues == []


def test_validation_result_out_with_issues():
    issue = IssueOut(
        issue_type="missing_objective",
        severity="critical",
        field="objective",
        explanation="No objective.",
    )
    result = ValidationResultOut(readiness_state="not_ready", issues=[issue])
    assert len(result.issues) == 1
    assert result.issues[0].issue_type == IssueType.MISSING_OBJECTIVE


def test_validation_result_out_invalid_readiness_state_raises():
    with pytest.raises(ValidationError):
        ValidationResultOut(readiness_state="done")


def test_validation_result_out_extra_key_rejected():
    with pytest.raises(ValidationError):
        ValidationResultOut(readiness_state="ready", note="nope")


# --------------------------------------------------------------------------- #
# ErrorResponse / ApiError
# --------------------------------------------------------------------------- #
def test_error_response_valid():
    err = ErrorResponse(error=ApiError(code="EXTRACTION_FAILED", message="boom"))
    assert err.error.code == "EXTRACTION_FAILED"
    assert err.error.message == "boom"


def test_api_error_extra_key_rejected():
    with pytest.raises(ValidationError):
        ApiError(code="X", message="y", detail="nope")


# --------------------------------------------------------------------------- #
# AnalyzeResponse full round-trip
# --------------------------------------------------------------------------- #
def test_analyze_response_round_trip():
    handoff = _make_structured_handoff(contradictions=[("deadline", "dependencies")])
    validation = ValidationResultOut(
        readiness_state="needs_clarification",
        issues=[
            IssueOut(
                issue_type="contradictory_information",
                severity="important",
                field="deadline",
                secondary_field="dependencies",
                explanation="Conflict.",
            )
        ],
    )
    response = AnalyzeResponse(handoff=handoff, validation=validation)
    dumped = response.model_dump()

    # Spot-check nested structure, a null value, and the contradictions list.
    assert dumped["handoff"]["objective"]["value"] == "Ship the feature"
    assert dumped["handoff"]["owner"]["value"] is None
    assert dumped["handoff"]["contradictions"] == [("deadline", "dependencies")]
    assert dumped["validation"]["readiness_state"] == "needs_clarification"
    assert dumped["validation"]["issues"][0]["secondary_field"] == "dependencies"
