"""Application-layer orchestration for handoff analysis.

This service composes the two existing pieces of the pipeline — AI extraction
and the deterministic readiness validator — into a single call. It contains NO
business logic: it computes no readiness or severity of its own, it does not
catch or transform extraction errors (they propagate to the caller), and it has
NO FastAPI or HTTP imports. Readiness is decided solely by ``validate_handoff``;
this service just wires the two steps together in order.
"""

from app.domain import StructuredHandoff, ValidationResult, validate_handoff
from app.extraction import ExtractionService


class AnalysisService:
    """Composes extraction + deterministic validation into one analyze() call."""

    def __init__(self, extraction_service: ExtractionService):
        self._extraction = extraction_service

    def analyze(self, text: str) -> tuple[StructuredHandoff, ValidationResult]:
        """Extract a StructuredHandoff from ``text`` and validate its readiness.

        Steps, in order:
        (a) delegate to extraction (may raise a typed ExtractionError, which is
            NOT caught here and propagates unchanged);
        (b) run the deterministic ``validate_handoff`` — the sole readiness
            authority — on the extracted handoff;
        (c) return both, without altering the validation verdict.
        """
        handoff = self._extraction.extract(text)  # may raise ExtractionError; do NOT catch
        result = validate_handoff(handoff)  # sole readiness authority
        return handoff, result
