"""Deterministic answer application + contradiction resolution (pure: no I/O, no AI, no web framework).

Applying an answer replaces a single target field's value and marks it PRESENT.
Resolving a contradiction removes exactly one declared (field_a, field_b) pair.
Neither path computes readiness or severity — that remains the sole
responsibility of the deterministic validator, which a caller runs separately
after these transformations. All functions are pure and operate on frozen domain
models via ``model_copy``.
"""

from pydantic import BaseModel, ConfigDict

from app.domain.handoff import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    StructuredHandoff,
)


class Answer(BaseModel):
    """A user's answer to a clarifying question: the target field + raw value (frozen)."""

    field: HandoffFieldName
    value: str

    model_config = ConfigDict(frozen=True)


class ClarificationError(Exception):
    """Base error for the clarification feature (answer application / resolution)."""


class EmptyAnswerError(ClarificationError):
    """Raised when an answer contains no usable content after normalization."""


class InvalidTargetFieldError(ClarificationError):
    """Raised when an answer targets something that is not one of the nine fields."""


class ContradictionNotFoundError(ClarificationError):
    """Raised when the exact contradiction pair to resolve is not declared."""


# The four list-valued fields and the five scalar fields. Together exhaustive
# over the nine HandoffFieldName members.
LIST_VALUED_FIELDS: frozenset[HandoffFieldName] = frozenset(
    {
        HandoffFieldName.INPUTS,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        HandoffFieldName.CONSTRAINTS,
        HandoffFieldName.DEPENDENCIES,
    }
)

SCALAR_FIELDS: frozenset[HandoffFieldName] = frozenset(
    {
        HandoffFieldName.OBJECTIVE,
        HandoffFieldName.OWNER,
        HandoffFieldName.EXPECTED_OUTPUT,
        HandoffFieldName.DEADLINE,
        HandoffFieldName.CONTEXT,
    }
)


def _coerce_value(field: HandoffFieldName, answer: str) -> str | list[str]:
    """Normalize a raw answer string into the shape the target field expects.

    List fields: split on newlines, strip each line, drop empties -> list[str];
    an empty result raises EmptyAnswerError. Scalar fields: strip; an empty
    result raises EmptyAnswerError. Pure.
    """
    if field in LIST_VALUED_FIELDS:
        items = [line.strip() for line in answer.split("\n")]
        items = [item for item in items if item != ""]
        if not items:
            raise EmptyAnswerError(
                f"The answer for '{field.value}' contained no usable list items."
            )
        return items

    stripped = answer.strip()
    if stripped == "":
        raise EmptyAnswerError(
            f"The answer for '{field.value}' was empty."
        )
    return stripped


def apply_answer(
    handoff: StructuredHandoff, field: HandoffFieldName, answer: str
) -> StructuredHandoff:
    """Return a copy of ``handoff`` with ``field`` set from ``answer`` and PRESENT.

    The target field is the authority: it is overwritten regardless of its
    original condition (even PRESENT), set to the coerced value with condition
    PRESENT. No other field is touched and ``contradictions`` is untouched. An
    empty answer raises EmptyAnswerError; a field that is not one of the nine
    raises InvalidTargetFieldError.
    """
    if not isinstance(field, HandoffFieldName) or field.value not in StructuredHandoff.model_fields:
        raise InvalidTargetFieldError(
            "The answer targeted a field that is not part of the handoff."
        )

    value = _coerce_value(field, answer)
    new_field = HandoffField(value=value, condition=FieldCondition.PRESENT)
    return handoff.model_copy(update={field.value: new_field})


def apply_answers(
    handoff: StructuredHandoff, answers: list[Answer]
) -> StructuredHandoff:
    """Apply each answer in turn (fold-left); last write wins per field.

    Order-independent across distinct fields; for the same field the last answer
    wins. Never touches ``contradictions``. Typed errors from ``apply_answer``
    propagate.
    """
    updated = handoff
    for answer in answers:
        updated = apply_answer(updated, answer.field, answer.value)
    return updated


def resolve_contradiction(
    handoff: StructuredHandoff,
    field_a: HandoffFieldName,
    field_b: HandoffFieldName,
) -> StructuredHandoff:
    """Return a copy of ``handoff`` with the exact (field_a, field_b) pair removed.

    The match is exact and order-sensitive against ``handoff.contradictions``. If
    the pair is not present, raise ContradictionNotFoundError and leave the
    handoff unchanged. Only the matching pair is removed (if duplicates of the
    same pair exist, all equal occurrences are filtered out — documented
    behavior); every field value/condition and all other pairs are preserved.
    """
    pair = (field_a, field_b)
    if pair not in handoff.contradictions:
        raise ContradictionNotFoundError(
            "The specified contradiction pair was not declared on this handoff."
        )
    remaining = [p for p in handoff.contradictions if p != pair]
    return handoff.model_copy(update={"contradictions": remaining})


def resolve_contradictions(
    handoff: StructuredHandoff,
    pairs: list[tuple[HandoffFieldName, HandoffFieldName]],
) -> StructuredHandoff:
    """Fold :func:`resolve_contradiction` over ``pairs``.

    Each pair must exist at the moment it is resolved, else
    ContradictionNotFoundError. Fields are never modified.
    """
    updated = handoff
    for field_a, field_b in pairs:
        updated = resolve_contradiction(updated, field_a, field_b)
    return updated
