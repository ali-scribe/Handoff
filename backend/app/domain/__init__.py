"""Core Handoff domain package: structured handoff model and deterministic validator."""

from app.domain.handoff import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    StructuredHandoff,
)
from app.domain.validation import (
    Issue,
    IssueSeverity,
    IssueType,
    ReadinessState,
    ValidationResult,
)
from app.domain.validator import validate_handoff

__all__ = [
    "FieldCondition",
    "HandoffFieldName",
    "HandoffField",
    "StructuredHandoff",
    "ReadinessState",
    "IssueSeverity",
    "IssueType",
    "Issue",
    "ValidationResult",
    "validate_handoff",
]
