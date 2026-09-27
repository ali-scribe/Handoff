"""Application-layer orchestration for the clarification flow (no web-framework imports).

Thin composition over the pure domain functions plus the sole readiness
authority ``validate_handoff``. This layer computes no readiness or severity of
its own: it runs the deterministic transforms (answers, then explicit
contradiction resolutions) and then defers to a single authoritative
re-validation.
"""

from app.domain import (
    HandoffFieldName,
    StructuredHandoff,
    ValidationResult,
    validate_handoff,
)
from app.domain.answers import (
    Answer,
    apply_answers,
    resolve_contradictions,
)
from app.domain.clarification import Question, generate_questions
from app.domain.formatter import format_handoff


def clarify(handoff: StructuredHandoff) -> list[Question]:
    """Validate ``handoff`` and generate clarifying questions from the result."""
    return generate_questions(validate_handoff(handoff))


def apply_and_revalidate(
    handoff: StructuredHandoff,
    answers: list[Answer],
    resolve_contradictions_pairs: list[tuple[HandoffFieldName, HandoffFieldName]]
    | None = None,
) -> tuple[StructuredHandoff, ValidationResult]:
    """Apply answers, then explicit contradiction resolutions, then re-validate.

    Order: (1) apply all answers; (2) resolve any explicitly requested
    contradiction pairs; (3) run the single authoritative ``validate_handoff``.
    Returns the updated handoff and its fresh validation result. Typed
    ClarificationErrors from the transforms propagate to the caller.
    """
    updated = apply_answers(handoff, answers)
    updated = resolve_contradictions(updated, resolve_contradictions_pairs or [])
    result = validate_handoff(updated)
    return updated, result


def format_ready_handoff(handoff: StructuredHandoff) -> str:
    """Validate ``handoff`` and render it to text (readiness read from validation)."""
    return format_handoff(handoff, validate_handoff(handoff))
