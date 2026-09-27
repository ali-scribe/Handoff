"""Provider interface: the ExtractionProvider Protocol the service depends on."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ExtractionProvider(Protocol):
    """Turns raw handoff text into raw extraction data (Req 11.1, 11.4).

    Implementations return a JSON-decoded object (a dict) that the
    ExtractionService validates against RawExtraction. Implementations are
    responsible ONLY for producing that raw data and for raising the typed
    extraction errors on provider/timeout/malformed-response conditions
    (Req 14.2, 14.3, 14.4). They MUST NOT construct a StructuredHandoff
    (Req 11.4) and MUST NOT compute readiness (Req 16).
    """

    def extract(self, text: str) -> dict:
        ...
