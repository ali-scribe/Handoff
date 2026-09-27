"""Deterministic handoff formatter (pure: no I/O, no AI, no web framework).

Renders a StructuredHandoff into a stable, human-readable text block. The
readiness header is READ from the supplied ValidationResult — the formatter
never computes readiness or severity. Same inputs always produce an identical
string (idempotent), and the formatter never invents missing information.
"""

from app.domain.handoff import (
    FieldCondition,
    HandoffFieldName,
    StructuredHandoff,
)
from app.domain.validation import ValidationResult

# Fixed section order (the nine fields in declaration order) with human labels.
_FIELD_LABELS: list[tuple[HandoffFieldName, str]] = [
    (HandoffFieldName.OBJECTIVE, "Objective"),
    (HandoffFieldName.OWNER, "Owner"),
    (HandoffFieldName.INPUTS, "Inputs"),
    (HandoffFieldName.EXPECTED_OUTPUT, "Expected Output"),
    (HandoffFieldName.DEADLINE, "Deadline"),
    (HandoffFieldName.ACCEPTANCE_CRITERIA, "Acceptance Criteria"),
    (HandoffFieldName.CONTEXT, "Context"),
    (HandoffFieldName.CONSTRAINTS, "Constraints"),
    (HandoffFieldName.DEPENDENCIES, "Dependencies"),
]

_MISSING_MARKER = "⚠ MISSING"
_NOT_APPLICABLE_MARKER = "n/a"


def _render_present_value(value) -> str:
    """Render a PRESENT field's value deterministically.

    List values render as one ``- item`` per line; scalar values render as-is;
    a ``None`` value (unusual for PRESENT) renders as an empty string.
    """
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    if value is None:
        return ""
    return str(value)


def _render_field(condition: FieldCondition, value) -> str:
    """Render one field body based purely on its condition and value."""
    if condition is FieldCondition.PRESENT:
        return _render_present_value(value)
    if condition is FieldCondition.MISSING:
        return _MISSING_MARKER
    if condition is FieldCondition.AMBIGUOUS:
        shown = _render_present_value(value)
        return f"⚠ UNCLEAR: {shown}"
    # NOT_APPLICABLE
    return _NOT_APPLICABLE_MARKER


def format_handoff(handoff: StructuredHandoff, validation: ValidationResult) -> str:
    """Render ``handoff`` into a stable text block; readiness is READ from ``validation``.

    Deterministic and idempotent. The readiness line displays
    ``validation.readiness_state.value`` verbatim (no derivation). Unresolved
    issues are listed briefly using their existing explanations. No missing
    information is ever invented.
    """
    lines: list[str] = []
    lines.append(f"Readiness: {validation.readiness_state.value}")
    lines.append("")

    for field_name, label in _FIELD_LABELS:
        field = getattr(handoff, field_name.value)
        body = _render_field(field.condition, field.value)
        if "\n" in body:
            # Multi-line list body: label header then indented items.
            lines.append(f"{label}:")
            lines.append(body)
        else:
            lines.append(f"{label}: {body}")

    if validation.issues:
        lines.append("")
        lines.append("Outstanding issues:")
        for issue in validation.issues:
            lines.append(f"- {issue.explanation}")

    return "\n".join(lines)
