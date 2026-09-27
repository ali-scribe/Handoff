"""Tests for the deterministic handoff formatter (app.domain.formatter)."""

import inspect

from app.domain import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    StructuredHandoff,
    validate_handoff,
)
from app.domain import formatter as formatter_module
from app.domain.formatter import format_handoff


def _field(value, condition):
    return HandoffField(value=value, condition=condition)


def _handoff(**overrides) -> StructuredHandoff:
    base = dict(
        objective=_field("Ship report", FieldCondition.PRESENT),
        owner=_field("Alice", FieldCondition.PRESENT),
        inputs=_field(["data.csv", "template.docx"], FieldCondition.PRESENT),
        expected_output=_field("A PDF", FieldCondition.PRESENT),
        deadline=_field("2025-03-01", FieldCondition.PRESENT),
        acceptance_criteria=_field(["matches template"], FieldCondition.PRESENT),
        context=_field("Q1", FieldCondition.PRESENT),
        constraints=_field(None, FieldCondition.NOT_APPLICABLE),
        dependencies=_field(["service-x"], FieldCondition.PRESENT),
    )
    base.update(overrides)
    return StructuredHandoff(**base)


def test_present_values_appear():
    h = _handoff()
    text = format_handoff(h, validate_handoff(h))
    assert "Ship report" in text
    assert "Alice" in text
    assert "data.csv" in text
    assert "template.docx" in text


def test_missing_field_shows_marker_no_fabrication():
    h = _handoff(objective=_field(None, FieldCondition.MISSING))
    text = format_handoff(h, validate_handoff(h))
    assert "Objective:" in text
    assert "⚠ MISSING" in text


def test_ambiguous_shows_value_but_marked():
    h = _handoff(deadline=_field("soon", FieldCondition.AMBIGUOUS))
    text = format_handoff(h, validate_handoff(h))
    assert "⚠ UNCLEAR: soon" in text


def test_not_applicable_shows_na():
    h = _handoff(constraints=_field(None, FieldCondition.NOT_APPLICABLE))
    text = format_handoff(h, validate_handoff(h))
    assert "Constraints: n/a" in text


def test_readiness_header_equals_validation_state():
    h = _handoff(objective=_field(None, FieldCondition.MISSING))
    validation = validate_handoff(h)
    text = format_handoff(h, validation)
    assert f"Readiness: {validation.readiness_state.value}" in text


def test_idempotent():
    h = _handoff(objective=_field(None, FieldCondition.MISSING))
    validation = validate_handoff(h)
    assert format_handoff(h, validation) == format_handoff(h, validation)


def test_no_invention_for_missing_field():
    h = _handoff(expected_output=_field(None, FieldCondition.MISSING))
    text = format_handoff(h, validate_handoff(h))
    # The label appears with the marker; no made-up value on that line.
    lines = [ln for ln in text.splitlines() if ln.startswith("Expected Output:")]
    assert lines == ["Expected Output: ⚠ MISSING"]


def test_formatter_does_not_compute_readiness():
    source = inspect.getsource(formatter_module)
    assert "validate_handoff" not in source
