"""Tests for the application-layer clarification flow (app.application.clarification_flow)."""

import inspect
import pytest

from app.domain import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    IssueType,
    ReadinessState,
    StructuredHandoff,
    validate_handoff,
)
from app.domain.answers import Answer
from app.application import clarification_flow
from app.application.clarification_flow import (
    apply_and_revalidate,
    clarify,
    format_ready_handoff,
)


def _field(value, condition):
    return HandoffField(value=value, condition=condition)


def _handoff(**overrides) -> StructuredHandoff:
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


def test_clarify_returns_questions_from_validation():
    h = _handoff(objective=_field(None, FieldCondition.MISSING))
    questions = clarify(h)
    assert any(q.field == HandoffFieldName.OBJECTIVE for q in questions)


def test_clarify_ready_handoff_no_questions():
    assert clarify(_handoff()) == []


def test_apply_and_revalidate_applies_answers_then_validates():
    h = _handoff(objective=_field(None, FieldCondition.MISSING))
    updated, validation = apply_and_revalidate(
        h, [Answer(field=HandoffFieldName.OBJECTIVE, value="Deliver the Q1 report")]
    )
    assert updated.objective.value == "Deliver the Q1 report"
    assert updated.objective.condition == FieldCondition.PRESENT
    # Readiness comes from validate_handoff on the updated handoff.
    assert validation.readiness_state == validate_handoff(updated).readiness_state


def test_resolving_last_contradiction_flips_critical_away():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    h = _handoff(contradictions=[pair])
    before = validate_handoff(h)
    assert before.readiness_state == ReadinessState.NOT_READY
    updated, validation = apply_and_revalidate(h, [], [pair])
    assert not any(
        i.issue_type == IssueType.CONTRADICTORY_INFORMATION for i in validation.issues
    )
    # Readiness is whatever the validator now decides on the resolved handoff.
    assert validation.readiness_state == validate_handoff(updated).readiness_state


def test_answers_alone_never_clear_contradictions():
    pair = (HandoffFieldName.DEADLINE, HandoffFieldName.CONSTRAINTS)
    h = _handoff(contradictions=[pair])
    updated, validation = apply_and_revalidate(
        h, [Answer(field=HandoffFieldName.DEADLINE, value="Friday")]
    )
    assert pair in updated.contradictions
    assert any(
        i.issue_type == IssueType.CONTRADICTORY_INFORMATION for i in validation.issues
    )


def test_format_ready_handoff_returns_text():
    text = format_ready_handoff(_handoff())
    assert "Readiness:" in text
    assert "Ship report" in text


def test_module_has_no_fastapi_import():
    source = inspect.getsource(clarification_flow)
    assert "fastapi" not in source


# --- Regression: a non-deadline answer must not make the handoff READY --------

def test_apply_and_revalidate_rejects_name_as_deadline():
    """End-to-end: answering the deadline question with 'Ali' keeps it not READY."""
    h = _handoff(deadline=_field("soon", FieldCondition.AMBIGUOUS))
    updated, validation = apply_and_revalidate(
        h, [Answer(field=HandoffFieldName.DEADLINE, value="Ali")]
    )
    assert validation.readiness_state != ReadinessState.READY
    assert any(i.issue_type == IssueType.VAGUE_DEADLINE for i in validation.issues)
    assert updated.deadline.condition == FieldCondition.AMBIGUOUS


def test_apply_and_revalidate_accepts_real_deadline():
    """A real deadline answer resolves the vague_deadline issue and reaches READY."""
    h = _handoff(deadline=_field("soon", FieldCondition.AMBIGUOUS))
    updated, validation = apply_and_revalidate(
        h, [Answer(field=HandoffFieldName.DEADLINE, value="2026-09-30")]
    )
    assert validation.readiness_state == ReadinessState.READY
    assert not any(
        i.issue_type == IssueType.VAGUE_DEADLINE for i in validation.issues
    )
    assert updated.deadline.condition == FieldCondition.PRESENT


# --- Regression: lone-word answers for description fields must not reach READY -

@pytest.mark.parametrize(
    "field",
    [
        HandoffFieldName.EXPECTED_OUTPUT,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        HandoffFieldName.DEPENDENCIES,
    ],
)
def test_apply_and_revalidate_rejects_lone_word_for_description_fields(field):
    """End-to-end: 'Ali' for a description field keeps the handoff not READY."""
    h = _handoff(**{field.value: _field(None, FieldCondition.MISSING)})
    updated, validation = apply_and_revalidate(
        h, [Answer(field=field, value="Ali")]
    )
    assert validation.readiness_state != ReadinessState.READY
    assert getattr(updated, field.value).condition == FieldCondition.MISSING


@pytest.mark.parametrize(
    "field,answer",
    [
        (HandoffFieldName.EXPECTED_OUTPUT, "A finished PDF report"),
        (HandoffFieldName.ACCEPTANCE_CRITERIA, "Matches the approved template"),
        (HandoffFieldName.DEPENDENCIES, "service-x"),
    ],
)
def test_apply_and_revalidate_accepts_valid_description_answers(field, answer):
    h = _handoff(**{field.value: _field(None, FieldCondition.MISSING)})
    updated, validation = apply_and_revalidate(
        h, [Answer(field=field, value=answer)]
    )
    assert validation.readiness_state == ReadinessState.READY
    assert getattr(updated, field.value).condition == FieldCondition.PRESENT
