"""Tests for the Structured Handoff domain model (HandoffField, StructuredHandoff).

Standard Pytest only (no Hypothesis / property-based testing). These tests exercise
the passive data model defined in ``app.domain.handoff``: it stores exactly what it
is given, pairs every field with exactly one FieldCondition, and never invents or
alters supplied content.
"""

import pytest
from pydantic import ValidationError

from app.domain.handoff import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    StructuredHandoff,
)

# The nine model fields, in the design's declared order.
NINE_FIELD_NAMES = [
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


def valid_field_kwargs() -> dict[str, HandoffField]:
    """Return a dict of nine valid HandoffFields keyed by StructuredHandoff field name.

    Kept DRY so individual tests can copy it and tweak/remove a single entry. Uses a
    mix of str, list[str], and None values to exercise the whole ``value`` union.
    """
    return {
        "objective": HandoffField(value="Ship the report", condition=FieldCondition.PRESENT),
        "owner": HandoffField(value="Alex", condition=FieldCondition.PRESENT),
        "inputs": HandoffField(value=["data.csv"], condition=FieldCondition.PRESENT),
        "expected_output": HandoffField(value="A PDF report", condition=FieldCondition.PRESENT),
        "deadline": HandoffField(value="Friday", condition=FieldCondition.PRESENT),
        "acceptance_criteria": HandoffField(
            value=["passes review"], condition=FieldCondition.PRESENT
        ),
        "context": HandoffField(value="Q3 numbers", condition=FieldCondition.PRESENT),
        "constraints": HandoffField(value=None, condition=FieldCondition.NOT_APPLICABLE),
        "dependencies": HandoffField(value=None, condition=FieldCondition.NOT_APPLICABLE),
    }


def valid_handoff() -> StructuredHandoff:
    """Construct a fully valid StructuredHandoff from the nine valid fields."""
    return StructuredHandoff(**valid_field_kwargs())


# ---------------------------------------------------------------------------
# 1) Construction success + round-trip (Req 1.4, 2.7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "a single string value",  # str
        ["one", "two", "three"],  # list[str]
        None,  # None
    ],
)
def test_handoff_field_round_trips_value_and_condition(value) -> None:
    """A constructed HandoffField reads back the identical value and condition.

    The model stores only what it is given and does not alter it (Req 1.4, 2.7).
    """
    field = HandoffField(value=value, condition=FieldCondition.PRESENT)
    assert field.value == value
    assert field.condition is FieldCondition.PRESENT


def test_structured_handoff_exposes_each_field_unchanged() -> None:
    """StructuredHandoff exposes each field's value and condition exactly as supplied.

    Confirms the model never invents or alters supplied content (Req 1.4, 2.7).
    """
    kwargs = valid_field_kwargs()
    handoff = StructuredHandoff(**kwargs)
    for name in NINE_FIELD_NAMES:
        supplied = kwargs[name]
        stored = getattr(handoff, name)
        assert stored.value == supplied.value
        assert stored.condition is supplied.condition


# ---------------------------------------------------------------------------
# 2) Construction failure raises ValidationError, no instance (Req 1.5, 1.6)
# ---------------------------------------------------------------------------


def test_invalid_field_condition_raises_validation_error() -> None:
    """An unknown FieldCondition value raises ValidationError (Req 1.6)."""
    with pytest.raises(ValidationError):
        HandoffField(value="x", condition="bogus")


def test_wrong_value_type_raises_validation_error() -> None:
    """A value that is not str | list[str] | None raises ValidationError (Req 1.5)."""
    with pytest.raises(ValidationError):
        HandoffField(value=123, condition=FieldCondition.PRESENT)


def test_omitted_condition_on_handoff_field_raises_validation_error() -> None:
    """Omitting the required ``condition`` raises ValidationError (Req 1.6)."""
    with pytest.raises(ValidationError):
        HandoffField(value="x")


@pytest.mark.parametrize("missing_field", NINE_FIELD_NAMES)
def test_structured_handoff_missing_required_field_raises(missing_field: str) -> None:
    """Omitting any one of the nine required fields raises ValidationError (Req 1.5, 1.6).

    Building the full valid kwargs and removing exactly one field per parameter
    proves each of the nine fields is required and no partial instance is produced.
    """
    kwargs = valid_field_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        StructuredHandoff(**kwargs)


# ---------------------------------------------------------------------------
# 3) Enum shape (Req 2.1, 1.1)
# ---------------------------------------------------------------------------


def test_field_condition_has_exactly_four_members() -> None:
    """FieldCondition is exactly {PRESENT, MISSING, AMBIGUOUS, NOT_APPLICABLE} (Req 2.1)."""
    assert len(FieldCondition) == 4
    assert {c.value for c in FieldCondition} == {
        "present",
        "missing",
        "ambiguous",
        "not_applicable",
    }


def test_handoff_field_name_has_exactly_nine_members() -> None:
    """HandoffFieldName is exactly the nine named fields (Req 1.1).

    Asserting the exact value set catches an accidental rename or drop of a field.
    """
    assert len(HandoffFieldName) == 9
    assert {n.value for n in HandoffFieldName} == {
        "objective",
        "owner",
        "inputs",
        "expected_output",
        "deadline",
        "acceptance_criteria",
        "context",
        "constraints",
        "dependencies",
    }


# ---------------------------------------------------------------------------
# 4) MISSING vs NOT_APPLICABLE are distinct (Req 2.4, 2.6)
# ---------------------------------------------------------------------------


def test_missing_and_not_applicable_are_distinct_members() -> None:
    """MISSING and NOT_APPLICABLE are different enum members (Req 2.4, 2.6)."""
    assert FieldCondition.MISSING != FieldCondition.NOT_APPLICABLE


@pytest.mark.parametrize(
    "condition",
    [FieldCondition.MISSING, FieldCondition.NOT_APPLICABLE],
)
def test_missing_and_not_applicable_both_storable_with_none_value(condition) -> None:
    """Both MISSING and NOT_APPLICABLE store with value=None and read back distinctly.

    The discriminator is the condition, never the emptiness of the value (Req 2.4, 2.6).
    """
    field = HandoffField(value=None, condition=condition)
    assert field.value is None
    assert field.condition is condition


# ---------------------------------------------------------------------------
# 5) Frozen behavior underpins later idempotence (Req 1.5)
# ---------------------------------------------------------------------------


def test_handoff_field_is_frozen() -> None:
    """Assigning to a HandoffField after construction raises ValidationError (frozen)."""
    field = HandoffField(value="x", condition=FieldCondition.PRESENT)
    with pytest.raises(ValidationError):
        field.value = "changed"


def test_structured_handoff_is_frozen() -> None:
    """Assigning to a StructuredHandoff field after construction raises (frozen)."""
    handoff = valid_handoff()
    with pytest.raises(ValidationError):
        handoff.objective = HandoffField(value="new", condition=FieldCondition.PRESENT)
