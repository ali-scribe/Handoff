"""Pure, deterministic translation layer: domain objects -> API DTOs.

This module contains ONLY translation. It maps already-valid domain results
(StructuredHandoff / ValidationResult and their parts) into the API wire DTOs
defined in ``app.api.schemas``. It performs no business logic:

* It does not compute readiness or issues — those are produced solely by
  ``validate_handoff`` upstream. This mapper never inspects, infers, normalizes,
  or repairs values.
* It copies values verbatim, including ``None`` and list values.
* It preserves the order of the declared contradiction pairs and never reorders
  or deduplicates them.
* It never mutates its inputs (the domain models are frozen; the mapper reads
  only).

Each function is an explicit, tiny hand-written translation — deliberately not a
generic/clever serializer — so the field-by-field wire contract stays obvious.
"""

from app.domain import HandoffField, Issue, StructuredHandoff, ValidationResult
from app.domain.clarification import Question
from app.api.schemas import (
    AnalyzeResponse,
    ApplyAnswersResponse,
    HandoffFieldOut,
    IssueOut,
    QuestionOut,
    StructuredHandoffIn,
    StructuredHandoffOut,
    ValidationResultOut,
)


def handoff_field_to_out(field: HandoffField) -> HandoffFieldOut:
    """Translate one domain HandoffField into its wire DTO.

    Copies ``value`` verbatim (including ``None`` and list values) and copies
    ``condition`` exactly. No inference.
    """
    return HandoffFieldOut(value=field.value, condition=field.condition)


def structured_handoff_to_out(handoff: StructuredHandoff) -> StructuredHandoffOut:
    """Translate a StructuredHandoff into its wire DTO.

    Maps all nine fields via :func:`handoff_field_to_out` and passes the declared
    contradiction pairs through unchanged, preserving order (no reordering, no
    deduplication).
    """
    return StructuredHandoffOut(
        objective=handoff_field_to_out(handoff.objective),
        owner=handoff_field_to_out(handoff.owner),
        inputs=handoff_field_to_out(handoff.inputs),
        expected_output=handoff_field_to_out(handoff.expected_output),
        deadline=handoff_field_to_out(handoff.deadline),
        acceptance_criteria=handoff_field_to_out(handoff.acceptance_criteria),
        context=handoff_field_to_out(handoff.context),
        constraints=handoff_field_to_out(handoff.constraints),
        dependencies=handoff_field_to_out(handoff.dependencies),
        contradictions=list(handoff.contradictions),
    )


def issue_to_out(issue: Issue) -> IssueOut:
    """Translate one domain Issue into its wire DTO.

    Preserves issue type, severity, primary field, secondary field (including
    ``None``), and explanation exactly.
    """
    return IssueOut(
        issue_type=issue.issue_type,
        severity=issue.severity,
        field=issue.field,
        secondary_field=issue.secondary_field,
        explanation=issue.explanation,
    )


def validation_result_to_out(result: ValidationResult) -> ValidationResultOut:
    """Translate a ValidationResult into its wire DTO.

    Preserves the readiness state exactly and maps each issue in order.
    """
    return ValidationResultOut(
        readiness_state=result.readiness_state,
        issues=[issue_to_out(issue) for issue in result.issues],
    )


def to_analyze_response(
    handoff: StructuredHandoff, result: ValidationResult
) -> AnalyzeResponse:
    """Combine a structured handoff and its validation into the response DTO."""
    return AnalyzeResponse(
        handoff=structured_handoff_to_out(handoff),
        validation=validation_result_to_out(result),
    )


# --- Clarification feature mappers --------------------------------------------
#
# Explicit, tiny translations mirroring the analyze mappers. The inbound mapper
# is the inverse of structured_handoff_to_out; question_to_out and
# to_apply_answers_response translate outbound. No business logic — no readiness
# is ever computed here.


def structured_handoff_in_to_domain(dto: StructuredHandoffIn) -> StructuredHandoff:
    """Translate an inbound StructuredHandoffIn into a domain StructuredHandoff.

    Inverse of :func:`structured_handoff_to_out`: builds a HandoffField from each
    of the nine inbound fields' value/condition and copies the declared
    contradiction pairs verbatim (order preserved).
    """

    def to_field(field_out: HandoffFieldOut) -> HandoffField:
        return HandoffField(value=field_out.value, condition=field_out.condition)

    return StructuredHandoff(
        objective=to_field(dto.objective),
        owner=to_field(dto.owner),
        inputs=to_field(dto.inputs),
        expected_output=to_field(dto.expected_output),
        deadline=to_field(dto.deadline),
        acceptance_criteria=to_field(dto.acceptance_criteria),
        context=to_field(dto.context),
        constraints=to_field(dto.constraints),
        dependencies=to_field(dto.dependencies),
        contradictions=list(dto.contradictions),
    )


def question_to_out(q: Question) -> QuestionOut:
    """Translate a domain Question into its wire DTO.

    Copies the primary field, secondary field (including ``None``), the issue
    types (tuple -> list, order preserved), and the text verbatim.
    """
    return QuestionOut(
        field=q.field,
        secondary_field=q.secondary_field,
        issue_types=list(q.issue_types),
        text=q.text,
    )


def to_apply_answers_response(
    handoff: StructuredHandoff, validation: ValidationResult
) -> ApplyAnswersResponse:
    """Combine an updated handoff and its validation into the apply-answers DTO.

    Parallel to :func:`to_analyze_response` but returns its OWN response type.
    """
    return ApplyAnswersResponse(
        handoff=structured_handoff_to_out(handoff),
        validation=validation_result_to_out(validation),
    )
