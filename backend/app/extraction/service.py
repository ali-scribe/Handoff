"""Extraction service: orchestrates text -> provider -> validated schema -> StructuredHandoff.

This module owns the *order* of the extraction pipeline and the pure mapping
from the validated AI output schema (RawExtraction) to the existing domain
model (StructuredHandoff). It depends only on the ExtractionProvider interface
and the domain model.

Boundary rule (Req 16): nothing here imports or calls the deterministic
readiness validator, produces a readiness-state value, or computes a readiness
verdict. The service's final product is a StructuredHandoff and nothing more.
Readiness is decided by the existing deterministic validator at a higher layer
that is out of scope here.
"""

from pydantic import ValidationError

from app.domain import HandoffField, StructuredHandoff
from app.extraction.errors import (
    EmptyInputError,
    MalformedResponseError,
    SchemaValidationError,
)
from app.extraction.provider import ExtractionProvider
from app.extraction.schema import RawExtraction, RawField


class ExtractionService:
    """Orchestrates extraction: text -> provider -> validated schema -> StructuredHandoff.

    Depends only on the ExtractionProvider interface and the domain model
    (Req 11.2). Produces a StructuredHandoff and STOPS — it does not import or
    call the readiness validator and never computes readiness
    (Req 16.1, 16.2, 16.3).
    """

    def __init__(self, provider: ExtractionProvider):
        self._provider = provider

    def extract(self, text: str) -> StructuredHandoff:
        """Extract raw handoff text into a validated StructuredHandoff.

        Ordered steps:

        (a) Reject empty/whitespace input BEFORE calling the provider, raising
            EmptyInputError (Req 1.2-1.4, 14.1). ``text.strip()`` catches
            all-whitespace input (Req 1.3).
        (b) Call ``provider.extract(text)``. The provider already surfaces
            typed ProviderFailureError / ProviderTimeoutError /
            MalformedResponseError; the service lets these propagate unchanged
            (Req 14.2-14.4).
        (c) A non-dict body is malformed (Req 14.4). A dict that fails Pydantic
            validation is a schema violation reported as SchemaValidationError
            with safe, structured detail — no repair, no guessing (Req 10.3,
            10.4). On any failure no StructuredHandoff is built and the
            readiness validator is never called (Req 10.5).
        (d) Convert the validated raw data into a StructuredHandoff (Req 8,
            10.6) and return it. No readiness anywhere (Req 16).
        """
        # (a) Reject empty/whitespace BEFORE calling the provider (Req 1.2-1.4, 14.1).
        if text is None or not text.strip():
            raise EmptyInputError("Handoff text must not be empty")

        # (b) Call the provider. Provider/timeout/malformed errors already come
        #     back as typed ExtractionErrors; let them propagate unchanged.
        raw_data = self._provider.extract(text)

        # (c) Validate raw data against the AI output schema (Req 10.2). No
        #     repair, no guessing (Req 10.4). A non-dict body is malformed;
        #     a dict that fails Pydantic is a schema violation.
        if not isinstance(raw_data, dict):
            raise MalformedResponseError(
                "The AI provider returned data that is not a JSON object"
            )
        try:
            raw = RawExtraction.model_validate(raw_data)
        except ValidationError as exc:
            # Report the failure as a schema violation with safe, structured
            # detail derived from Pydantic (field locations + error kinds),
            # never raw provider text (Req 10.3, 14.7).
            raise SchemaValidationError.from_pydantic(exc) from None

        # (d) Convert validated raw data -> StructuredHandoff (pure) (Req 8, 10.6).
        return raw_to_structured(raw)


def raw_to_structured(raw: RawExtraction) -> StructuredHandoff:
    """Pure mapping: RawExtraction -> StructuredHandoff (Req 8, 10.6).

    Deterministic, no I/O, no inference. Builds one HandoffField(value,
    condition) per field straight from the validated raw data and passes
    contradictions through unchanged (Req 9.1, 9.2). It modifies nothing: values
    and conditions are copied verbatim (Req 10.6). Constructing StructuredHandoff
    re-validates via the frozen domain models, so identical validated input
    yields an equal StructuredHandoff every time (Req 13.3).

    It never imports or calls the readiness validator and never computes
    readiness (Req 16.1, 16.2).
    """

    def field(rf: RawField) -> HandoffField:
        return HandoffField(value=rf.value, condition=rf.condition)

    return StructuredHandoff(
        objective=field(raw.objective),
        owner=field(raw.owner),
        inputs=field(raw.inputs),
        expected_output=field(raw.expected_output),
        deadline=field(raw.deadline),
        acceptance_criteria=field(raw.acceptance_criteria),
        context=field(raw.context),
        constraints=field(raw.constraints),
        dependencies=field(raw.dependencies),
        contradictions=list(raw.contradictions),
    )
