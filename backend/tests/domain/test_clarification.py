"""Tests for deterministic clarification-question generation (app.domain.clarification)."""

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
from app.domain.clarification import Question, generate_questions


def _field(value, condition):
    return HandoffField(value=value, condition=condition)


def _all_present_handoff(**overrides) -> StructuredHandoff:
    base = dict(
        objective=_field("Ship report", FieldCondition.PRESENT),
        owner=_field("Alice", FieldCondition.PRESENT),
        inputs=_field(["data.csv"], FieldCondition.PRESENT),
        expected_output=_field("A PDF", FieldCondition.PRESENT),
        deadline=_field("2025-03-01", FieldCondition.PRESENT),
        acceptance_criteria=_field(["matches template"], FieldCondition.PRESENT),
        context=_field("Q1", FieldCondition.PRESENT),
        constraints=_field(None, FieldCondition.NOT_APPLICABLE),
        dependencies=_field(["service-x"], FieldCondition.PRESENT),
    )
    base.update(overrides)
    return StructuredHandoff(**base)


# --- Mapping: every IssueType maps to a question ------------------------------

_ISSUE_TYPE_CASES = [
    (
        IssueType.MISSING_OBJECTIVE,
        IssueSeverity.CRITICAL,
        HandoffFieldName.OBJECTIVE,
        None,
        "objective of this work",
    ),
    (
        IssueType.VAGUE_OBJECTIVE,
        IssueSeverity.IMPORTANT,
        HandoffFieldName.OBJECTIVE,
        None,
        "objective is unclear",
    ),
    (
        IssueType.VAGUE_ACTION_LANGUAGE,
        IssueSeverity.MINOR,
        HandoffFieldName.EXPECTED_OUTPUT,
        None,
        "wording is vague",
    ),
    (
        IssueType.MISSING_REQUIRED_INPUT,
        IssueSeverity.CRITICAL,
        HandoffFieldName.INPUTS,
        None,
        "inputs are required",
    ),
    (
        IssueType.MISSING_EXPECTED_OUTPUT,
        IssueSeverity.CRITICAL,
        HandoffFieldName.EXPECTED_OUTPUT,
        None,
        "expected output or deliverable",
    ),
    (
        IssueType.VAGUE_DEADLINE,
        IssueSeverity.IMPORTANT,
        HandoffFieldName.DEADLINE,
        None,
        "When is this due",
    ),
    (
        IssueType.MISSING_ACCEPTANCE_CRITERIA,
        IssueSeverity.IMPORTANT,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        None,
        "acceptance criteria",
    ),
    (
        IssueType.UNRESOLVED_DEPENDENCY,
        IssueSeverity.IMPORTANT,
        HandoffFieldName.DEPENDENCIES,
        None,
        "depend on",
    ),
    (
        IssueType.AMBIGUOUS_OWNERSHIP,
        IssueSeverity.IMPORTANT,
        HandoffFieldName.OWNER,
        None,
        "responsible",
    ),
    (
        IssueType.CONTRADICTORY_INFORMATION,
        IssueSeverity.CRITICAL,
        HandoffFieldName.OBJECTIVE,
        HandoffFieldName.DEADLINE,
        "conflict",
    ),
]


def test_every_issue_type_maps_to_a_question():
    for issue_type, severity, field, secondary, substring in _ISSUE_TYPE_CASES:
        result = ValidationResult(
            readiness_state=ReadinessState.NOT_READY,
            issues=[
                Issue(
                    issue_type=issue_type,
                    severity=severity,
                    field=field,
                    secondary_field=secondary,
                    explanation="x",
                )
            ],
        )
        questions = generate_questions(result)
        assert len(questions) == 1, issue_type
        q = questions[0]
        assert q.field == field
        assert issue_type in q.issue_types
        assert substring.lower() in q.text.lower(), issue_type


def test_contradiction_question_references_both_fields():
    result = ValidationResult(
        readiness_state=ReadinessState.NOT_READY,
        issues=[
            Issue(
                issue_type=IssueType.CONTRADICTORY_INFORMATION,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.DEADLINE,
                secondary_field=HandoffFieldName.CONSTRAINTS,
                explanation="x",
            )
        ],
    )
    q = generate_questions(result)[0]
    assert q.field == HandoffFieldName.DEADLINE
    assert q.secondary_field == HandoffFieldName.CONSTRAINTS
    assert HandoffFieldName.DEADLINE.value in q.text
    assert HandoffFieldName.CONSTRAINTS.value in q.text


def test_dedupe_ambiguous_objective_yields_single_question_merged_types():
    # An AMBIGUOUS objective yields vague_objective (IMPORTANT) +
    # vague_action_language (MINOR) via validate_handoff -> ONE question.
    handoff = _all_present_handoff(
        objective=_field("do stuff", FieldCondition.AMBIGUOUS)
    )
    validation = validate_handoff(handoff)
    questions = generate_questions(validation)
    objective_qs = [q for q in questions if q.field == HandoffFieldName.OBJECTIVE]
    assert len(objective_qs) == 1
    q = objective_qs[0]
    assert IssueType.VAGUE_OBJECTIVE in q.issue_types
    assert IssueType.VAGUE_ACTION_LANGUAGE in q.issue_types
    # Text comes from the IMPORTANT (vague_objective) template.
    assert "objective is unclear" in q.text.lower()


def test_prioritization_critical_before_important_before_minor():
    result = ValidationResult(
        readiness_state=ReadinessState.NOT_READY,
        issues=[
            # MINOR on expected_output (declared later in field order)
            Issue(
                issue_type=IssueType.VAGUE_ACTION_LANGUAGE,
                severity=IssueSeverity.MINOR,
                field=HandoffFieldName.EXPECTED_OUTPUT,
                explanation="x",
            ),
            # IMPORTANT on deadline
            Issue(
                issue_type=IssueType.VAGUE_DEADLINE,
                severity=IssueSeverity.IMPORTANT,
                field=HandoffFieldName.DEADLINE,
                explanation="x",
            ),
            # CRITICAL on inputs
            Issue(
                issue_type=IssueType.MISSING_REQUIRED_INPUT,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.INPUTS,
                explanation="x",
            ),
        ],
    )
    questions = generate_questions(result)
    assert [q.field for q in questions] == [
        HandoffFieldName.INPUTS,  # CRITICAL
        HandoffFieldName.DEADLINE,  # IMPORTANT
        HandoffFieldName.EXPECTED_OUTPUT,  # MINOR
    ]


def test_prioritization_tie_break_by_field_order():
    # Two CRITICAL issues on different fields -> ordered by declaration order.
    result = ValidationResult(
        readiness_state=ReadinessState.NOT_READY,
        issues=[
            Issue(
                issue_type=IssueType.MISSING_EXPECTED_OUTPUT,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.EXPECTED_OUTPUT,
                explanation="x",
            ),
            Issue(
                issue_type=IssueType.MISSING_OBJECTIVE,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.OBJECTIVE,
                explanation="x",
            ),
        ],
    )
    questions = generate_questions(result)
    assert [q.field for q in questions] == [
        HandoffFieldName.OBJECTIVE,  # declared before expected_output
        HandoffFieldName.EXPECTED_OUTPUT,
    ]


def test_hard_cap_of_five_keeps_highest_severities():
    # Seven distinct-field issues: 3 CRITICAL, 3 IMPORTANT, 1 MINOR -> keep 5:
    # the 3 CRITICAL then 2 IMPORTANT (by field order).
    issues = [
        Issue(issue_type=IssueType.MISSING_OBJECTIVE, severity=IssueSeverity.CRITICAL,
              field=HandoffFieldName.OBJECTIVE, explanation="x"),
        Issue(issue_type=IssueType.MISSING_REQUIRED_INPUT, severity=IssueSeverity.CRITICAL,
              field=HandoffFieldName.INPUTS, explanation="x"),
        Issue(issue_type=IssueType.MISSING_EXPECTED_OUTPUT, severity=IssueSeverity.CRITICAL,
              field=HandoffFieldName.EXPECTED_OUTPUT, explanation="x"),
        Issue(issue_type=IssueType.AMBIGUOUS_OWNERSHIP, severity=IssueSeverity.IMPORTANT,
              field=HandoffFieldName.OWNER, explanation="x"),
        Issue(issue_type=IssueType.VAGUE_DEADLINE, severity=IssueSeverity.IMPORTANT,
              field=HandoffFieldName.DEADLINE, explanation="x"),
        Issue(issue_type=IssueType.MISSING_ACCEPTANCE_CRITERIA, severity=IssueSeverity.IMPORTANT,
              field=HandoffFieldName.ACCEPTANCE_CRITERIA, explanation="x"),
        Issue(issue_type=IssueType.UNRESOLVED_DEPENDENCY, severity=IssueSeverity.MINOR,
              field=HandoffFieldName.DEPENDENCIES, explanation="x"),
    ]
    result = ValidationResult(readiness_state=ReadinessState.NOT_READY, issues=issues)
    questions = generate_questions(result)
    assert len(questions) == 5
    fields = [q.field for q in questions]
    # The 3 CRITICAL fields come first (by field order): objective, inputs, expected_output.
    assert fields[:3] == [
        HandoffFieldName.OBJECTIVE,
        HandoffFieldName.INPUTS,
        HandoffFieldName.EXPECTED_OUTPUT,
    ]
    # Next two are the earliest-declared IMPORTANT fields: owner, deadline.
    assert fields[3:] == [HandoffFieldName.OWNER, HandoffFieldName.DEADLINE]
    # The MINOR dependencies question was dropped.
    assert HandoffFieldName.DEPENDENCIES not in fields


def test_zero_issues_yields_no_questions():
    result = ValidationResult(readiness_state=ReadinessState.READY, issues=[])
    assert generate_questions(result) == []


def test_present_and_not_applicable_fields_never_asked():
    # A fully-ready handoff (constraints NOT_APPLICABLE, everything else PRESENT)
    # yields no issues, hence no questions about any of those fields.
    handoff = _all_present_handoff()
    validation = validate_handoff(handoff)
    assert validation.readiness_state == ReadinessState.READY
    questions = generate_questions(validation)
    assert questions == []


def test_question_model_is_frozen():
    q = Question(
        field=HandoffFieldName.OBJECTIVE,
        issue_types=(IssueType.MISSING_OBJECTIVE,),
        text="x",
    )
    try:
        q.text = "y"
    except Exception:
        return
    raise AssertionError("Question should be frozen")
