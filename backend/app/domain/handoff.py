"""Structured Handoff domain model: field conditions, HandoffField, and StructuredHandoff."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FieldCondition(str, Enum):
    """The information state of a single handoff field (Req 2.1)."""

    PRESENT = "present"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"


class HandoffFieldName(str, Enum):
    """The nine conceptual fields of a structured handoff (Req 1.1, 6.3)."""

    OBJECTIVE = "objective"
    OWNER = "owner"
    INPUTS = "inputs"
    EXPECTED_OUTPUT = "expected_output"
    DEADLINE = "deadline"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    CONTEXT = "context"
    CONSTRAINTS = "constraints"
    DEPENDENCIES = "dependencies"


class HandoffField(BaseModel):
    """Pairs one supplied value with exactly one FieldCondition (Req 1.2, 2.2, 2.7).

    The model stores only what it is given: the ``value`` comes solely from the
    constructor and ``condition`` must always be supplied by the caller. It performs
    no inference and never derives the condition from the value.
    """

    value: str | list[str] | None = None
    condition: FieldCondition  # required — no default (Req 1.6, 2.2)

    model_config = ConfigDict(frozen=True)  # immutable


class StructuredHandoff(BaseModel):
    """A structured work request: nine HandoffFields plus declared contradictions (Req 1.1, 1.3, 1.7).

    All nine fields are required *fields of the model*; each therefore always
    carries exactly one FieldCondition (Req 1.2, 2.2). "Required per model" is
    distinct from "required for the task" — the latter is a validator policy, not
    a concern of this model. This model is a passive data container: it stores
    only the HandoffFields it is given and the ``contradictions`` list it is
    handed. It performs no inference — in particular it does not discover
    contradictions; ``contradictions`` holds only the field pairs a caller has
    explicitly declared to conflict (Req 4.8).
    """

    objective: HandoffField
    owner: HandoffField
    inputs: HandoffField
    expected_output: HandoffField
    deadline: HandoffField
    acceptance_criteria: HandoffField
    context: HandoffField
    constraints: HandoffField
    dependencies: HandoffField

    # Optional, explicitly declared contradictions between two fields (Req 4.8).
    contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] = Field(
        default_factory=list
    )

    model_config = ConfigDict(frozen=True)
