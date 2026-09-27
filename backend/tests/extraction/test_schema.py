"""Tests for the AI output schema: RawField and RawExtraction (Req 3, 5, 6, 9, 10).

Standard pytest only. These tests exercise the validation *shape* of the AI
boundary: which conditions are accepted, which field names are legal in a
contradiction pair, and which payloads are rejected. They deliberately do NOT
touch conversion to StructuredHandoff — that belongs to a later service task.
"""

import pytest
from pydantic import ValidationError

from app.domain import FieldCondition, HandoffFieldName
from app.extraction.schema import RawExtraction, RawField


# The nine handoff fields, in domain order. Used to build valid payloads and to
# parametrize the "drop one required field" rejection case.
NINE_FIELDS = [
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


def valid_payload() -> dict:
    """Return a fresh, fully valid nine-field RawExtraction payload.

    Every field is ``present`` with a simple value; the list-valued fields carry
    lists. ``contradictions`` starts empty. Tests copy this and mutate one thing
    so each rejection is isolated to a single cause.
    """
    return {
        "objective": {"value": "Fix the login bug", "condition": "present"},
        "owner": {"value": "Alice", "condition": "present"},
        "inputs": {"value": ["repo access", "staging creds"], "condition": "present"},
        "expected_output": {"value": "A working login", "condition": "present"},
        "deadline": {"value": "Friday", "condition": "present"},
        "acceptance_criteria": {"value": ["users can log in"], "condition": "present"},
        "context": {"value": "Users are locked out", "condition": "present"},
        "constraints": {"value": ["no downtime"], "condition": "present"},
        "dependencies": {"value": ["auth service"], "condition": "present"},
        "contradictions": [],
    }


# --- 1. Valid complete extraction ----------------------------------------


def test_valid_complete_extraction_validates_and_round_trips():
    """A full valid payload validates and preserves values + conditions."""
    payload = valid_payload()

    raw = RawExtraction.model_validate(payload)

    assert raw.objective.value == "Fix the login bug"
    assert raw.objective.condition == FieldCondition.PRESENT
    assert raw.inputs.value == ["repo access", "staging creds"]
    assert raw.inputs.condition == FieldCondition.PRESENT
    assert raw.contradictions == []
    # Every field is populated and present.
    for name in NINE_FIELDS:
        assert getattr(raw, name).condition == FieldCondition.PRESENT


# --- 2. All four field conditions accepted -------------------------------


@pytest.mark.parametrize(
    "condition",
    ["present", "missing", "ambiguous", "not_applicable"],
)
def test_raw_field_accepts_every_valid_condition(condition):
    """Each of the four FieldConditions validates and is stored as given."""
    field = RawField.model_validate({"value": "something", "condition": condition})

    assert field.condition == FieldCondition(condition)


# --- 3. Invalid condition rejected ---------------------------------------


def test_invalid_condition_string_rejected():
    """A condition outside the four allowed values fails validation (Req 3.2, 10.3)."""
    with pytest.raises(ValidationError):
        RawField.model_validate({"value": "x", "condition": "urgent"})


# --- 4. Invalid contradiction field name rejected ------------------------


def test_invalid_contradiction_field_name_rejected():
    """A contradiction pair naming a non-field fails validation (Req 9.4)."""
    payload = valid_payload()
    payload["contradictions"] = [["objective", "banana"]]

    with pytest.raises(ValidationError):
        RawExtraction.model_validate(payload)


def test_valid_contradiction_pair_accepted():
    """A contradiction pair of two real field names validates and is kept."""
    payload = valid_payload()
    payload["contradictions"] = [["objective", "deadline"]]

    raw = RawExtraction.model_validate(payload)

    assert raw.contradictions == [
        (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    ]


# --- 5. Extra / unknown fields rejected ----------------------------------


def test_extra_top_level_key_rejected():
    """An unexpected top-level key is rejected (extra='forbid', Req 10.3)."""
    payload = valid_payload()
    payload["readiness"] = "ready"

    with pytest.raises(ValidationError):
        RawExtraction.model_validate(payload)


def test_extra_key_inside_field_rejected():
    """An unexpected key inside a RawField object is rejected (extra='forbid')."""
    payload = valid_payload()
    payload["objective"] = {
        "value": "Fix the login bug",
        "condition": "present",
        "confidence": 0.9,
    }

    with pytest.raises(ValidationError):
        RawExtraction.model_validate(payload)


# --- 6. Missing required schema field rejected ---------------------------


@pytest.mark.parametrize("field_name", NINE_FIELDS)
def test_missing_required_field_rejected(field_name):
    """Dropping any one of the nine fields fails validation (Req 10.3)."""
    payload = valid_payload()
    del payload[field_name]

    with pytest.raises(ValidationError):
        RawExtraction.model_validate(payload)


# --- 7. AMBIGUOUS retains value ------------------------------------------


def test_ambiguous_field_retains_value():
    """An ambiguous field keeps its value rather than blanking it (Req 6)."""
    field = RawField.model_validate({"value": "soon", "condition": "ambiguous"})

    assert field.condition == FieldCondition.AMBIGUOUS
    assert field.value == "soon"


# --- 8 & 9. MISSING and NOT_APPLICABLE can represent None ----------------


def test_missing_field_can_be_none():
    """A missing field may carry value=None (Req 5.1)."""
    field = RawField.model_validate({"value": None, "condition": "missing"})

    assert field.condition == FieldCondition.MISSING
    assert field.value is None


def test_not_applicable_field_can_be_none():
    """A not-applicable field may carry value=None (Req 5.2)."""
    field = RawField.model_validate({"value": None, "condition": "not_applicable"})

    assert field.condition == FieldCondition.NOT_APPLICABLE
    assert field.value is None


def test_missing_and_not_applicable_are_distinct_conditions():
    """MISSING and NOT_APPLICABLE stay distinct stored conditions (Req 5, 7)."""
    missing = RawField.model_validate({"value": None, "condition": "missing"})
    not_applicable = RawField.model_validate(
        {"value": None, "condition": "not_applicable"}
    )

    assert missing.condition != not_applicable.condition


# --- 10. List-valued fields behave per contract --------------------------


def test_list_valued_field_preserves_list():
    """A list value validates and the list is preserved (value is str|list|None)."""
    field = RawField.model_validate({"value": ["a", "b"], "condition": "present"})

    assert field.value == ["a", "b"]


def test_str_valued_field_validates():
    """A plain string value also validates (the value union allows str)."""
    field = RawField.model_validate({"value": "just a string", "condition": "present"})

    assert field.value == "just a string"


# --- 11. Malformed nested field data rejected ----------------------------


def test_non_object_field_rejected():
    """A field given a bare string (not a RawField object) fails validation."""
    payload = valid_payload()
    payload["inputs"] = "not-a-field-object"

    with pytest.raises(ValidationError):
        RawExtraction.model_validate(payload)


def test_condition_of_wrong_type_rejected():
    """A condition supplied as an int is not a valid FieldCondition value."""
    with pytest.raises(ValidationError):
        RawField.model_validate({"value": "x", "condition": 3})


# --- 12. No silent coercion / repair -------------------------------------


def test_missing_condition_is_not_defaulted():
    """Omitting condition raises — no default is invented (Req 3.1)."""
    with pytest.raises(ValidationError):
        RawField.model_validate({"value": "x"})


def test_invalid_condition_is_not_coerced_to_valid():
    """A wholly invalid condition is rejected, never silently mapped to a valid one."""
    with pytest.raises(ValidationError):
        RawField.model_validate({"value": "x", "condition": "URGENT_NOW"})
