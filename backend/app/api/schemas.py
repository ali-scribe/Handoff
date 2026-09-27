"""API-owned request/response models for the handoff analysis endpoint.

These are separate from the domain and extraction Pydantic models: the HTTP
boundary owns its own DTOs so the wire contract can evolve independently of the
internal domain objects. We REUSE the domain enums (FieldCondition,
HandoffFieldName, ReadinessState, IssueSeverity, IssueType) for typing,
validation, and serialization — an out-of-vocabulary value therefore fails
validation naturally — but we do NOT reuse the domain BaseModels themselves.

Config choice: every model sets ``extra="forbid"`` so malformed payloads with
unknown keys are rejected rather than silently accepted (mirrors the
extra="forbid" style in app/extraction/schema.py). Models are intentionally left
mutable (not frozen): these are response/request DTOs and FastAPI serialization
works either way, so we keep it simple and do not freeze any of them.
"""

from pydantic import BaseModel, ConfigDict

from app.domain import (
    FieldCondition,
    HandoffFieldName,
    IssueSeverity,
    IssueType,
    ReadinessState,
)


class AnalyzeRequest(BaseModel):
    """The request body for the analysis endpoint: raw handoff text.

    ``text`` is a required plain string. This model deliberately does NOT enforce
    empty/whitespace rules — that business rule lives in ExtractionService. A
    missing ``text`` or a non-string value fails Pydantic validation naturally.
    """

    text: str

    model_config = ConfigDict(extra="forbid")


class HandoffFieldOut(BaseModel):
    """One structured field on the wire: a value plus exactly one condition.

    Mirrors the domain HandoffField shape. Null values are preserved (e.g. a
    MISSING or NOT_APPLICABLE field may carry ``value=None``) and ``condition``
    is required, reusing FieldCondition so a bad condition string fails
    validation.
    """

    value: str | list[str] | None = None
    condition: FieldCondition  # required; no default

    model_config = ConfigDict(extra="forbid")


class StructuredHandoffOut(BaseModel):
    """The full structured handoff on the wire: nine fields + declared contradictions.

    The nine fields appear in domain order. ``contradictions`` reuses
    HandoffFieldName so a bad field name in a pair fails validation; pairs are
    preserved exactly as given.
    """

    objective: HandoffFieldOut
    owner: HandoffFieldOut
    inputs: HandoffFieldOut
    expected_output: HandoffFieldOut
    deadline: HandoffFieldOut
    acceptance_criteria: HandoffFieldOut
    context: HandoffFieldOut
    constraints: HandoffFieldOut
    dependencies: HandoffFieldOut

    contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] = []

    model_config = ConfigDict(extra="forbid")


class IssueOut(BaseModel):
    """One detected problem on the wire.

    Carries the issue type, severity, associated field, and a human-readable
    explanation. ``secondary_field`` is populated only for contradiction issues.
    """

    issue_type: IssueType
    severity: IssueSeverity
    field: HandoffFieldName
    secondary_field: HandoffFieldName | None = None
    explanation: str

    model_config = ConfigDict(extra="forbid")


class ValidationResultOut(BaseModel):
    """The validation verdict on the wire: a readiness state plus the issue list."""

    readiness_state: ReadinessState
    issues: list[IssueOut] = []

    model_config = ConfigDict(extra="forbid")


class AnalyzeResponse(BaseModel):
    """The successful analysis response: the structured handoff and its validation."""

    handoff: StructuredHandoffOut
    validation: ValidationResultOut

    model_config = ConfigDict(extra="forbid")


class ApiError(BaseModel):
    """The inner payload of a structured API error: a stable code and a message."""

    code: str
    message: str

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    """The structured API error envelope wrapping a single ApiError.

    Defined now so the contract is available; the actual error handlers and
    status mapping are implemented in a later task.
    """

    error: ApiError

    model_config = ConfigDict(extra="forbid")


# --- Clarification feature DTOs ------------------------------------------------
#
# Inbound + outbound wire models for the three clarification endpoints. All set
# extra="forbid" (mirroring the analyze DTOs) so unknown keys are rejected, and
# all reuse the domain enums for typed validation. StructuredHandoffIn is the
# inbound mirror of StructuredHandoffOut and reuses HandoffFieldOut for its
# nine fields.


class StructuredHandoffIn(BaseModel):
    """Inbound structured handoff: nine fields + declared contradictions.

    Mirrors StructuredHandoffOut; reuses HandoffFieldOut for each field so
    value/condition are validated on the way in. ``contradictions`` defaults to
    an empty list and reuses HandoffFieldName so a bad field name fails.
    """

    objective: HandoffFieldOut
    owner: HandoffFieldOut
    inputs: HandoffFieldOut
    expected_output: HandoffFieldOut
    deadline: HandoffFieldOut
    acceptance_criteria: HandoffFieldOut
    context: HandoffFieldOut
    constraints: HandoffFieldOut
    dependencies: HandoffFieldOut

    contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] = []

    model_config = ConfigDict(extra="forbid")


class QuestionOut(BaseModel):
    """One clarifying question on the wire.

    ``secondary_field`` is present only for contradiction questions.
    ``issue_types`` is the ordered list of issue types merged into the question.
    """

    field: HandoffFieldName
    secondary_field: HandoffFieldName | None = None
    issue_types: list[IssueType]
    text: str

    model_config = ConfigDict(extra="forbid")


class AnswerIn(BaseModel):
    """A user's answer to a clarifying question: the target field + raw value."""

    field: HandoffFieldName
    value: str

    model_config = ConfigDict(extra="forbid")


class ClarifyRequest(BaseModel):
    """Request body for POST /handoff/clarify."""

    handoff: StructuredHandoffIn

    model_config = ConfigDict(extra="forbid")


class ClarifyResponse(BaseModel):
    """Response body for POST /handoff/clarify: the generated questions."""

    questions: list[QuestionOut]

    model_config = ConfigDict(extra="forbid")


class ApplyAnswersRequest(BaseModel):
    """Request body for POST /handoff/apply-answers.

    Carries the handoff, the answers to apply, and any explicit contradiction
    pairs to resolve. Both lists default to empty.
    """

    handoff: StructuredHandoffIn
    answers: list[AnswerIn] = []
    resolve_contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] = []

    model_config = ConfigDict(extra="forbid")


class ApplyAnswersResponse(BaseModel):
    """Response body for POST /handoff/apply-answers.

    A DEDICATED DTO (not AnalyzeResponse): the updated handoff plus its fresh
    validation verdict.
    """

    handoff: StructuredHandoffOut
    validation: ValidationResultOut

    model_config = ConfigDict(extra="forbid")


class FormatRequest(BaseModel):
    """Request body for POST /handoff/format."""

    handoff: StructuredHandoffIn

    model_config = ConfigDict(extra="forbid")


class FormatResponse(BaseModel):
    """Response body for POST /handoff/format: the rendered text block."""

    text: str

    model_config = ConfigDict(extra="forbid")
