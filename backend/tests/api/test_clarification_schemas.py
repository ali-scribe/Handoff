"""Tests for clarification API schemas + mappers (round-trips, validation)."""

import pytest
from pydantic import ValidationError

from app.domain import (
    FieldCondition,
    HandoffFieldName,
    IssueType,
)
from app.domain.clarification import Question
from app.api.mapping import (
    question_to_out,
    structured_handoff_in_to_domain,
    to_apply_answers_response,
)
from app.api.schemas import (
    AnalyzeResponse,
    ApplyAnswersResponse,
    HandoffFieldOut,
    StructuredHandoffIn,
)
from app.domain import validate_handoff


def _handoff_in(**overrides) -> StructuredHandoffIn:
    base = dict(
        objective=HandoffFieldOut(value="Ship report", condition=FieldCondition.PRESENT),
        owner=HandoffFieldOut(value="Alice", condition=FieldCondition.PRESENT),
        inputs=HandoffFieldOut(value=["data.csv"], condition=FieldCondition.PRESENT),
        expected_output=HandoffFieldOut(value="A PDF", condition=FieldCondition.PRESENT),
        deadline=HandoffFieldOut(value="2025-03-01", condition=FieldCondition.PRESENT),
        acceptance_criteria=HandoffFieldOut(value=["ok"], condition=FieldCondition.PRESENT),
        context=HandoffFieldOut(value="Q1", condition=FieldCondition.PRESENT),
        constraints=HandoffFieldOut(value=None, condition=FieldCondition.NOT_APPLICABLE),
        dependencies=HandoffFieldOut(value=["service-x"], condition=FieldCondition.PRESENT),
    )
    base.update(overrides)
    return StructuredHandoffIn(**base)


def test_structured_handoff_in_to_domain_round_trip():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    dto = _handoff_in(contradictions=[pair])
    domain = structured_handoff_in_to_domain(dto)
    assert domain.objective.value == "Ship report"
    assert domain.objective.condition == FieldCondition.PRESENT
    assert domain.inputs.value == ["data.csv"]
    assert domain.constraints.condition == FieldCondition.NOT_APPLICABLE
    assert domain.contradictions == [pair]
    # All nine present.
    for name in HandoffFieldName:
        assert getattr(domain, name.value) is not None


def test_question_to_out_preserves_fields():
    q = Question(
        field=HandoffFieldName.OBJECTIVE,
        secondary_field=HandoffFieldName.DEADLINE,
        issue_types=(IssueType.CONTRADICTORY_INFORMATION, IssueType.VAGUE_OBJECTIVE),
        text="please clarify",
    )
    out = question_to_out(q)
    assert out.field == HandoffFieldName.OBJECTIVE
    assert out.secondary_field == HandoffFieldName.DEADLINE
    assert out.issue_types == [
        IssueType.CONTRADICTORY_INFORMATION,
        IssueType.VAGUE_OBJECTIVE,
    ]
    assert out.text == "please clarify"


def test_to_apply_answers_response_type():
    domain = structured_handoff_in_to_domain(_handoff_in())
    validation = validate_handoff(domain)
    resp = to_apply_answers_response(domain, validation)
    assert isinstance(resp, ApplyAnswersResponse)
    assert not isinstance(resp, AnalyzeResponse)
    assert resp.handoff.objective.value == "Ship report"


def test_invalid_condition_rejected():
    with pytest.raises(ValidationError):
        HandoffFieldOut(value="x", condition="not_a_condition")


def test_extra_key_rejected_on_inbound():
    payload = _handoff_in().model_dump()
    payload["surprise"] = "boom"
    with pytest.raises(ValidationError):
        StructuredHandoffIn(**payload)
