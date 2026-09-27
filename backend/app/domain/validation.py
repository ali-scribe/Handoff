"""Validation result models: readiness states, issue severities, Issue, and ValidationResult."""

from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.domain.handoff import HandoffFieldName


class ReadinessState(str, Enum):
    """The overall readiness verdict for a handoff (Req 3.1)."""

    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    NOT_READY = "not_ready"


class IssueSeverity(str, Enum):
    """How much a detected issue impacts executability (Req 5.1)."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    MINOR = "minor"


class IssueType(str, Enum):
    """The detectable issue types produced by the validator (Req 4)."""

    MISSING_OBJECTIVE = "missing_objective"
    VAGUE_OBJECTIVE = "vague_objective"
    MISSING_REQUIRED_INPUT = "missing_required_input"
    MISSING_EXPECTED_OUTPUT = "missing_expected_output"
    VAGUE_DEADLINE = "vague_deadline"
    MISSING_ACCEPTANCE_CRITERIA = "missing_acceptance_criteria"
    UNRESOLVED_DEPENDENCY = "unresolved_dependency"
    CONTRADICTORY_INFORMATION = "contradictory_information"
    AMBIGUOUS_OWNERSHIP = "ambiguous_ownership"
    VAGUE_ACTION_LANGUAGE = "vague_action_language"


class Issue(BaseModel):
    """One detected problem with a handoff (Req 6.3, 4.8).

    Carries the issue type, its severity, the associated field, and a
    human-readable explanation. ``secondary_field`` is populated only for
    contradiction issues, referencing the second conflicting field (Req 4.8).
    """

    issue_type: IssueType
    severity: IssueSeverity
    field: HandoffFieldName  # the associated field (Req 6.3)
    secondary_field: HandoffFieldName | None = None  # only for contradictions (Req 4.8)
    explanation: str  # human-readable (Req 6.3)

    model_config = ConfigDict(frozen=True)


class ValidationResult(BaseModel):
    """The validator's output: a readiness verdict plus the full issue list (Req 6.1, 6.2, 6.5)."""

    readiness_state: ReadinessState  # Req 6.1
    issues: list[Issue]  # Req 6.2

    model_config = ConfigDict(frozen=True)
