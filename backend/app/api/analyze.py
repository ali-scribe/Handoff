"""HTTP route for handoff analysis: POST /handoff/analyze.

The route is intentionally THIN. It validates the request body via
``AnalyzeRequest``, delegates the actual work to ``AnalysisService`` (obtained
via dependency injection so tests can override it), maps the domain result to
the wire DTO, and returns it. No extraction or readiness logic lives inline —
that stays in the extraction/domain layers behind the service. Typed
ExtractionErrors are allowed to propagate to the registered error handler.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_analysis_service
from app.api.mapping import to_analyze_response
from app.api.schemas import AnalyzeRequest, AnalyzeResponse
from app.application.analysis import AnalysisService

router = APIRouter()


@router.post("/handoff/analyze", response_model=AnalyzeResponse)
def analyze_handoff(
    request: AnalyzeRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalyzeResponse:
    """Analyze raw handoff text and return the structured handoff + validation."""
    handoff, result = service.analyze(request.text)
    return to_analyze_response(handoff, result)
