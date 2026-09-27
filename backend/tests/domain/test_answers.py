"""Tests for deterministic answer application + contradiction resolution (app.domain.answers)."""

import pytest

from app.domain import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    IssueType,
    StructuredHandoff,
    validate_handoff,
)
from app.domain.answers import (
    Answer,
    ContradictionNotFoundError,
    EmptyAnswerError,
    apply_answer,
    apply_answers,
    resolve_contradiction,
    resolve_contradictions,
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


# (a) applying to a contradiction-involved field preserves contradictions
def test_apply_answer_preserves_contradictions():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    h = _handoff(
        objective=_field("do stuff", FieldCondition.AMBIGUOUS),
        contradictions=[pair],
    )
    updated = apply_answer(h, HandoffFieldName.OBJECTIVE, "Ship the Q1 report by EOD")
    assert updated.contradictions == [pair]


# (b) answering a field never clears contradictions
def test_answering_field_never_clears_contradictions():
    pair = (HandoffFieldName.DEADLINE, HandoffFieldName.CONSTRAINTS)
    h = _handoff(contradictions=[pair])
    updated = apply_answers(
        h, [Answer(field=HandoffFieldName.DEADLINE, value="Friday 5pm")]
    )
    assert updated.contradictions == [pair]


# (c) resolve removes exactly targeted pair; nothing else changes
def test_resolve_contradiction_removes_only_targeted_pair():
    p1 = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    p2 = (HandoffFieldName.INPUTS, HandoffFieldName.EXPECTED_OUTPUT)
    h = _handoff(contradictions=[p1, p2])
    updated = resolve_contradiction(h, *p1)
    assert updated.contradictions == [p2]
    # Every field's value/condition identical.
    for name in HandoffFieldName:
        before = getattr(h, name.value)
        after = getattr(updated, name.value)
        assert before.value == after.value
        assert before.condition == after.condition


# (d) wrong-order / non-existent pair raises and leaves handoff unchanged
def test_resolve_wrong_order_raises_and_unchanged():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    h = _handoff(contradictions=[pair])
    with pytest.raises(ContradictionNotFoundError):
        resolve_contradiction(h, HandoffFieldName.DEADLINE, HandoffFieldName.OBJECTIVE)
    # Original unchanged.
    assert h.contradictions == [pair]


def test_resolve_nonexistent_pair_raises():
    h = _handoff(contradictions=[])
    with pytest.raises(ContradictionNotFoundError):
        resolve_contradiction(h, HandoffFieldName.INPUTS, HandoffFieldName.OWNER)


# (e) target-field authority
def test_apply_answer_overwrites_present_field():
    h = _handoff(objective=_field("old objective", FieldCondition.PRESENT))
    updated = apply_answer(h, HandoffFieldName.OBJECTIVE, "new objective")
    assert updated.objective.value == "new objective"
    assert updated.objective.condition == FieldCondition.PRESENT


def test_apply_answer_sets_present_from_missing():
    h = _handoff(objective=_field(None, FieldCondition.MISSING))
    updated = apply_answer(h, HandoffFieldName.OBJECTIVE, "the goal")
    assert updated.objective.value == "the goal"
    assert updated.objective.condition == FieldCondition.PRESENT


def test_apply_answer_sets_present_from_ambiguous():
    h = _handoff(objective=_field("vague", FieldCondition.AMBIGUOUS))
    updated = apply_answer(h, HandoffFieldName.OBJECTIVE, "clear goal")
    assert updated.objective.condition == FieldCondition.PRESENT
    assert updated.objective.value == "clear goal"


# (f) list vs scalar coercion
def test_list_field_coercion():
    h = _handoff(inputs=_field(None, FieldCondition.MISSING))
    updated = apply_answer(h, HandoffFieldName.INPUTS, "a\nb\n\n c ")
    assert updated.inputs.value == ["a", "b", "c"]


def test_scalar_field_coercion_strips():
    h = _handoff()
    updated = apply_answer(h, HandoffFieldName.OWNER, "  hi  ")
    assert updated.owner.value == "hi"


# (g) empty answers
def test_empty_scalar_answer_raises():
    h = _handoff()
    with pytest.raises(EmptyAnswerError):
        apply_answer(h, HandoffFieldName.OBJECTIVE, "   ")


def test_blank_list_answer_raises():
    h = _handoff()
    with pytest.raises(EmptyAnswerError):
        apply_answer(h, HandoffFieldName.INPUTS, "\n  \n\n")


# (h) unrelated fields preserved
def test_unrelated_fields_preserved():
    h = _handoff()
    updated = apply_answer(h, HandoffFieldName.OWNER, "Bob")
    for name in HandoffFieldName:
        if name == HandoffFieldName.OWNER:
            continue
        assert getattr(updated, name.value).value == getattr(h, name.value).value
        assert getattr(updated, name.value).condition == getattr(h, name.value).condition


# (i) batch order-independence and last-wins
def test_apply_answers_order_independent_distinct_fields():
    h = _handoff()
    a = Answer(field=HandoffFieldName.OWNER, value="Bob")
    b = Answer(field=HandoffFieldName.OBJECTIVE, value="Deliver X")
    ab = apply_answers(h, [a, b])
    ba = apply_answers(h, [b, a])
    assert ab.model_dump() == ba.model_dump()


def test_apply_answers_same_field_last_wins():
    h = _handoff()
    updated = apply_answers(
        h,
        [
            Answer(field=HandoffFieldName.OWNER, value="Bob"),
            Answer(field=HandoffFieldName.OWNER, value="Carol"),
        ],
    )
    assert updated.owner.value == "Carol"


def test_resolve_contradictions_batch():
    p1 = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    p2 = (HandoffFieldName.INPUTS, HandoffFieldName.OWNER)
    h = _handoff(contradictions=[p1, p2])
    updated = resolve_contradictions(h, [p1, p2])
    assert updated.contradictions == []


# (j) after resolve + validate_handoff, the contradiction CRITICAL issue is gone
def test_resolve_then_validate_removes_contradiction_issue():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    h = _handoff(contradictions=[pair])
    before = validate_handoff(h)
    assert any(
        i.issue_type == IssueType.CONTRADICTORY_INFORMATION for i in before.issues
    )
    updated = resolve_contradiction(h, *pair)
    after = validate_handoff(updated)
    assert not any(
        i.issue_type == IssueType.CONTRADICTORY_INFORMATION for i in after.issues
    )
