"""AI output schema: the RawField and RawExtraction Pydantic models validated at the boundary."""

from pydantic import BaseModel, ConfigDict

from app.domain import FieldCondition, HandoffFieldName


class RawField(BaseModel):
    """One field as the AI reports it: a value plus exactly one condition.

    Mirrors the domain HandoffField shape but lives on the AI side of the
    boundary. Reusing FieldCondition means an out-of-vocabulary condition
    string fails validation here (Req 3.2, 10.3). A MISSING/NOT_APPLICABLE
    field may carry value=None (Req 5.1, 5.2); an AMBIGUOUS field retains its
    extracted value (Req 6).
    """

    value: str | list[str] | None = None
    condition: FieldCondition  # required; no default (Req 3.1)

    model_config = ConfigDict(extra="forbid")


class RawExtraction(BaseModel):
    """The full raw AI output: nine RawFields + optional declared contradictions.

    This is the AI_Output_Schema (Req 10.1). It maps 1:1 to StructuredHandoff
    but is validated FIRST, before any domain object exists (Req 10.2). Reusing
    HandoffFieldName in the contradiction pairs means a bad field name fails
    validation here (Req 9.4). extra='forbid' rejects unexpected top-level keys,
    turning "surprise" payload keys into a schema-validation failure (Req 10.3).
    """

    objective: RawField
    owner: RawField
    inputs: RawField
    expected_output: RawField
    deadline: RawField
    acceptance_criteria: RawField
    context: RawField
    constraints: RawField
    dependencies: RawField

    contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] = []

    model_config = ConfigDict(extra="forbid")
