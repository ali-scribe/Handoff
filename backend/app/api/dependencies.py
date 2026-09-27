"""FastAPI dependency wiring for the analysis endpoint.

Builds the production ``AnalysisService`` (real Gemini-backed extraction) for
the route via ``Depends(get_analysis_service)``. Tests swap in a fake by
overriding this factory through ``app.dependency_overrides``.

Construction is LAZY: the Gemini config/API key is only needed when the real
provider is actually built (when this factory is called), not at import time.
Keeping ``get_analysis_service`` a plain factory makes it trivially overridable.
"""

from app.application.analysis import AnalysisService
from app.extraction import ExtractionService, GeminiProvider


def get_analysis_service() -> AnalysisService:
    """Build the production AnalysisService backed by the real Gemini provider."""
    return AnalysisService(ExtractionService(GeminiProvider()))
