"""HTTP routes for the clarification engine (thin: validate DTO -> map -> domain -> map back).

Three POST endpoints operate on a supplied handoff (no extraction, no Gemini):

* /handoff/clarify       -> generate clarifying questions
* /handoff/apply-answers -> apply answers + resolve contradictions + re-validate
* /handoff/format        -> render the handoff to text

No readiness logic and no validation call live inline — that stays in
the application/domain layers. Typed ClarificationErrors raised by the
application layer propagate to the registered exception handler.
"""

from fastapi import APIRouter

from app.api.mapping import (
    question_to_out,
    structured_handoff_in_to_domain,
    to_apply_answers_response,
)
from app.api.schemas import (
    ApplyAnswersRequest,
    ApplyAnswersResponse,
    ClarifyRequest,
    ClarifyResponse,
    FormatRequest,
    FormatResponse,
)
from app.application.clarification_flow import (
    apply_and_revalidate,
    clarify,
    format_ready_handoff,
)
from app.domain.answers import Answer

router = APIRouter()


@router.post("/handoff/clarify", response_model=ClarifyResponse)
def clarify_handoff(request: ClarifyRequest) -> ClarifyResponse:
    """Generate clarifying questions for the supplied handoff."""
    handoff = structured_handoff_in_to_domain(request.handoff)
    questions = clarify(handoff)
    return ClarifyResponse(questions=[question_to_out(q) for q in questions])


@router.post("/handoff/apply-answers", response_model=ApplyAnswersResponse)
def apply_answers_endpoint(request: ApplyAnswersRequest) -> ApplyAnswersResponse:
    """Apply answers + explicit contradiction resolutions, then re-validate."""
    handoff = structured_handoff_in_to_domain(request.handoff)
    answers = [Answer(field=a.field, value=a.value) for a in request.answers]
    updated, validation = apply_and_revalidate(
        handoff, answers, request.resolve_contradictions
    )
    return to_apply_answers_response(updated, validation)


@router.post("/handoff/format", response_model=FormatResponse)
def format_handoff_endpoint(request: FormatRequest) -> FormatResponse:
    """Render the supplied handoff to a stable text block."""
    handoff = structured_handoff_in_to_domain(request.handoff)
    text = format_ready_handoff(handoff)
    return FormatResponse(text=text)
