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


# --- (k) Semantic field validity: a non-empty answer must not blindly satisfy -
#         a field. Deadline is the semantically-typed case (regression for the
#         "answering deadline with a person's name makes it READY" bug).

def _not_ready_handoff_needing_deadline() -> StructuredHandoff:
    """A handoff whose ONLY problem is a vague (AMBIGUOUS) deadline.

    Everything required is present, so readiness hinges entirely on the deadline
    answer: a real deadline makes it READY; a non-deadline answer must not.
    """
    return _handoff(deadline=_field("soon", FieldCondition.AMBIGUOUS))


def test_name_answer_for_deadline_does_not_make_field_present():
    h = _not_ready_handoff_needing_deadline()
    updated = apply_answer(h, HandoffFieldName.DEADLINE, "Ali")
    # The arbitrary name is retained as the value but NOT accepted as a valid
    # deadline: it stays AMBIGUOUS, never PRESENT.
    assert updated.deadline.value == "Ali"
    assert updated.deadline.condition == FieldCondition.AMBIGUOUS


def test_name_answer_for_deadline_does_not_make_handoff_ready():
    """Regression: 'Ali' as a deadline must keep the vague_deadline issue."""
    h = _not_ready_handoff_needing_deadline()
    updated = apply_answer(h, HandoffFieldName.DEADLINE, "Ali")
    result = validate_handoff(updated)
    assert result.readiness_state != "ready"
    assert any(
        i.issue_type == IssueType.VAGUE_DEADLINE for i in result.issues
    )


@pytest.mark.parametrize(
    "bad_value",
    ["Ali", "Bob Smith", "the backend team", "soon", "whenever", "John Doe"],
)
def test_non_deadline_answers_stay_ambiguous(bad_value):
    h = _not_ready_handoff_needing_deadline()
    updated = apply_answer(h, HandoffFieldName.DEADLINE, bad_value)
    assert updated.deadline.condition == FieldCondition.AMBIGUOUS


@pytest.mark.parametrize(
    "good_value",
    [
        "2025-03-01",
        "Friday 5pm",
        "next week",
        "by EOD",
        "March 1",
        "Q1 2026",
        "tomorrow",
        "3/1/2025",
        "15:30",
        "end of the month",
        "the 15th",
    ],
)
def test_real_deadline_answers_are_present_and_can_make_ready(good_value):
    h = _not_ready_handoff_needing_deadline()
    updated = apply_answer(h, HandoffFieldName.DEADLINE, good_value)
    assert updated.deadline.condition == FieldCondition.PRESENT
    # With a real deadline supplied and nothing else outstanding, the handoff
    # becomes READY and the vague_deadline issue is gone.
    result = validate_handoff(updated)
    assert result.readiness_state == "ready"
    assert not any(
        i.issue_type == IssueType.VAGUE_DEADLINE for i in result.issues
    )


# --- (l) The other eight fields still accept their valid answers as PRESENT ----
#         (the fix must not change non-deadline field behavior).

@pytest.mark.parametrize(
    "field,answer",
    [
        (HandoffFieldName.OBJECTIVE, "Ship the Q1 report"),
        (HandoffFieldName.OWNER, "Alice Chen"),
        (HandoffFieldName.EXPECTED_OUTPUT, "A finished PDF report"),
        (HandoffFieldName.CONTEXT, "For the Q1 board meeting"),
        (HandoffFieldName.INPUTS, "data.csv\ntemplate.docx"),
        (HandoffFieldName.ACCEPTANCE_CRITERIA, "Matches the approved template"),
        (HandoffFieldName.DEPENDENCIES, "service-x"),
        (HandoffFieldName.CONSTRAINTS, "No external vendors"),
    ],
)
def test_non_deadline_fields_accept_valid_answers_as_present(field, answer):
    h = _handoff(**{field.value: _field(None, FieldCondition.MISSING)})
    updated = apply_answer(h, field, answer)
    assert getattr(updated, field.value).condition == FieldCondition.PRESENT


# --- (m) Description-type fields reject a lone bare word (false-READY fix) -----
#         expected_output / acceptance_criteria / dependencies answered with a
#         bare name like "Ali" must NOT satisfy the field. No name/keyword lists:
#         the rule is simply that a lone alphabetic word lacks substance.

def _handoff_needing(field: HandoffFieldName) -> StructuredHandoff:
    """A handoff whose only outstanding problem is the given required field.

    The field is MISSING (so it is unsatisfied) and everything else is present,
    so readiness hinges entirely on the answer supplied for that field.
    """
    missing_value = None
    return _handoff(**{field.value: _field(missing_value, FieldCondition.MISSING)})


@pytest.mark.parametrize(
    "field",
    [
        HandoffFieldName.EXPECTED_OUTPUT,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        HandoffFieldName.DEPENDENCIES,
    ],
)
def test_lone_word_answer_is_not_present(field):
    h = _handoff_needing(field)
    updated = apply_answer(h, field, "Ali")
    # Chosen so the EXISTING validator still flags the field: these three react
    # to MISSING, so a lone-word answer is classified MISSING (not PRESENT), and
    # its junk value is cleared.
    assert getattr(updated, field.value).condition == FieldCondition.MISSING
    assert getattr(updated, field.value).value is None


@pytest.mark.parametrize(
    "field",
    [
        HandoffFieldName.EXPECTED_OUTPUT,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        HandoffFieldName.DEPENDENCIES,
    ],
)
def test_lone_word_answer_does_not_make_handoff_ready(field):
    """Regression: a bare name must not clear the field's issue / reach READY."""
    h = _handoff_needing(field)
    updated = apply_answer(h, field, "Ali")
    result = validate_handoff(updated)
    assert result.readiness_state != "ready"


@pytest.mark.parametrize(
    "field,answer",
    [
        # Multi-word descriptions.
        (HandoffFieldName.EXPECTED_OUTPUT, "A finished PDF report"),
        (HandoffFieldName.ACCEPTANCE_CRITERIA, "Matches the approved template"),
        (HandoffFieldName.ACCEPTANCE_CRITERIA, "matches template"),
        (HandoffFieldName.DEPENDENCIES, "the staging payment service"),
        # Single-token identifiers (digits / punctuation) count as substance.
        (HandoffFieldName.EXPECTED_OUTPUT, "report.pdf"),
        (HandoffFieldName.DEPENDENCIES, "service-x"),
        # List answers: a substantive item (even one) is accepted.
        (HandoffFieldName.DEPENDENCIES, "payment-api\nauth-service"),
        (HandoffFieldName.ACCEPTANCE_CRITERIA, "All tests pass\nreviewed by lead"),
    ],
)
def test_valid_description_answers_stay_present(field, answer):
    h = _handoff_needing(field)
    updated = apply_answer(h, field, answer)
    assert getattr(updated, field.value).condition == FieldCondition.PRESENT


@pytest.mark.parametrize(
    "field,answer",
    [
        # These fields are OUT OF SCOPE for the substance rule: a lone word is a
        # legitimate answer and must stay PRESENT (no regression).
        (HandoffFieldName.OWNER, "Alice"),
        (HandoffFieldName.OBJECTIVE, "Ship"),
        (HandoffFieldName.CONTEXT, "Q1"),
        (HandoffFieldName.INPUTS, "data"),
        (HandoffFieldName.CONSTRAINTS, "budget"),
    ],
)
def test_lone_word_still_present_for_non_description_fields(field, answer):
    h = _handoff_needing(field) if field != HandoffFieldName.CONSTRAINTS else _handoff(
        constraints=_field(None, FieldCondition.MISSING)
    )
    updated = apply_answer(h, field, answer)
    assert getattr(updated, field.value).condition == FieldCondition.PRESENT


# --- (n) Dependencies: an explicit "no dependencies" answer is VALID ----------
#         The dependencies clarification question invites "state there are none",
#         so such answers resolve the field as NOT_APPLICABLE (not MISSING), and
#         the handoff can reach READY. "Ali" stays insufficient; "service-x"
#         stays a real dependency.

@pytest.mark.parametrize(
    "answer",
    ["None", "none", "none needed", "no dependencies", "no external dependencies", "n/a", "nil"],
)
def test_no_dependency_answer_is_not_applicable(answer):
    h = _handoff(dependencies=_field(None, FieldCondition.MISSING))
    updated = apply_answer(h, HandoffFieldName.DEPENDENCIES, answer)
    assert updated.dependencies.condition == FieldCondition.NOT_APPLICABLE


@pytest.mark.parametrize(
    "answer",
    ["None", "none needed", "no dependencies", "no external dependencies"],
)
def test_no_dependency_answer_can_make_handoff_ready(answer):
    h = _handoff(dependencies=_field(None, FieldCondition.MISSING))
    updated = apply_answer(h, HandoffFieldName.DEPENDENCIES, answer)
    result = validate_handoff(updated)
    assert result.readiness_state == "ready"
    assert not any(
        i.issue_type == IssueType.UNRESOLVED_DEPENDENCY for i in result.issues
    )


def test_dependencies_lone_name_still_insufficient():
    """Guard: the no-dependency override must not accept an arbitrary name."""
    h = _handoff(dependencies=_field(None, FieldCondition.MISSING))
    updated = apply_answer(h, HandoffFieldName.DEPENDENCIES, "Ali")
    assert updated.dependencies.condition == FieldCondition.MISSING


@pytest.mark.parametrize(
    "answer",
    ["service-x", "notification-service", "needs the staging database"],
)
def test_real_dependency_answer_stays_present(answer):
    """Guard: real dependencies (incl. ones with an 'n' word) stay PRESENT."""
    h = _handoff(dependencies=_field(None, FieldCondition.MISSING))
    updated = apply_answer(h, HandoffFieldName.DEPENDENCIES, answer)
    assert updated.dependencies.condition == FieldCondition.PRESENT


@pytest.mark.parametrize(
    "field",
    [HandoffFieldName.EXPECTED_OUTPUT, HandoffFieldName.ACCEPTANCE_CRITERIA],
)
def test_no_value_phrasing_not_special_for_other_description_fields(field):
    """The no-dependency override is scoped to dependencies only; 'None' for the
    other description fields remains insufficient (unchanged behavior)."""
    h = _handoff(**{field.value: _field(None, FieldCondition.MISSING)})
    updated = apply_answer(h, field, "None")
    assert getattr(updated, field.value).condition == FieldCondition.MISSING
