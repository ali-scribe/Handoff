"""Pure, testable evaluation metrics for Handoff.

These functions operate on already-collected predictions; they perform no I/O
and never call the AI or the validator themselves. "Critical" is defined ONLY by
the existing domain model: an issue whose severity is ``IssueSeverity.CRITICAL``.
Field identity uses the existing ``HandoffFieldName`` values. Nothing here
redefines readiness, severity, or field names.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.domain import Issue, IssueSeverity, ReadinessState


# --- Prediction record ------------------------------------------------------


@dataclass(frozen=True)
class CasePrediction:
    """One case's expected labels plus what the real pipeline predicted.

    ``predicted_readiness`` / ``predicted_issues`` are None only when the case
    errored (infrastructure failure). Errored cases are excluded from all
    metric denominators by the functions below.
    """

    id: str
    category: str
    expected_readiness: ReadinessState
    expected_critical_fields: tuple[str, ...] = ()
    predicted_readiness: ReadinessState | None = None
    predicted_issues: tuple[Issue, ...] = ()
    error: str | None = None

    @property
    def evaluated(self) -> bool:
        """True when the case ran successfully (no infrastructure error)."""
        return self.error is None and self.predicted_readiness is not None


def _evaluated(predictions):
    """Return only the successfully-evaluated predictions."""
    return [p for p in predictions if p.evaluated]


# --- Readiness accuracy -----------------------------------------------------


def readiness_accuracy(predictions) -> dict:
    """Fraction of evaluated cases where predicted readiness == expected.

    Returns ``{"correct", "total", "accuracy"}``. ``accuracy`` is None when
    there are no evaluated cases (avoids division by zero).
    """
    evaluated = _evaluated(predictions)
    total = len(evaluated)
    correct = sum(
        1 for p in evaluated if p.predicted_readiness == p.expected_readiness
    )
    accuracy = (correct / total) if total else None
    return {"correct": correct, "total": total, "accuracy": accuracy}


# --- Critical issue detection ----------------------------------------------


def _critical_fields_in_issues(issues) -> set[str]:
    """Field names flagged by a CRITICAL issue (incl. secondary_field).

    Uses the existing Issue/IssueSeverity model only. secondary_field is
    included so a contradiction (which names two fields) counts for either.
    """
    flagged: set[str] = set()
    for issue in issues:
        if issue.severity is IssueSeverity.CRITICAL:
            flagged.add(issue.field.value)
            if issue.secondary_field is not None:
                flagged.add(issue.secondary_field.value)
    return flagged


def detected_critical_fields(prediction: CasePrediction) -> list[str]:
    """The subset of a case's expected critical fields that were detected."""
    flagged = _critical_fields_in_issues(prediction.predicted_issues)
    return [f for f in prediction.expected_critical_fields if f in flagged]


def critical_issue_detection(predictions) -> dict:
    """How many expected critical fields the pipeline flagged as CRITICAL.

    Aggregated over evaluated cases. Returns
    ``{"expected_critical_count", "detected_critical_count",
    "critical_detection_rate"}``. Rate is None when no critical fields are
    expected (avoids division by zero).
    """
    expected_count = 0
    detected_count = 0
    for p in _evaluated(predictions):
        flagged = _critical_fields_in_issues(p.predicted_issues)
        for f in p.expected_critical_fields:
            expected_count += 1
            if f in flagged:
                detected_count += 1
    rate = (detected_count / expected_count) if expected_count else None
    return {
        "expected_critical_count": expected_count,
        "detected_critical_count": detected_count,
        "critical_detection_rate": rate,
    }


# --- False positives / negatives -------------------------------------------


def false_positive_rate(predictions) -> dict:
    """False positive = expected READY but predicted non-READY.

    Denominator is the number of evaluated READY cases. Rate is None when there
    are zero READY cases (avoids division by zero).
    """
    ready = [
        p
        for p in _evaluated(predictions)
        if p.expected_readiness == ReadinessState.READY
    ]
    fp = sum(1 for p in ready if p.predicted_readiness != ReadinessState.READY)
    rate = (fp / len(ready)) if ready else None
    return {
        "false_positive_count": fp,
        "ready_case_count": len(ready),
        "false_positive_rate": rate,
    }


def false_negative_count(predictions) -> int:
    """False negative = expected non-READY but predicted READY.

    A plain count over evaluated cases (useful safety signal even though it is
    not a primary rate metric).
    """
    return sum(
        1
        for p in _evaluated(predictions)
        if p.expected_readiness != ReadinessState.READY
        and p.predicted_readiness == ReadinessState.READY
    )


# --- Category breakdown -----------------------------------------------------


def category_breakdown(predictions) -> dict:
    """Readiness accuracy grouped by category.

    Generic over categories: ``{category: {"correct", "total", "accuracy"}}``
    for every category present among evaluated cases. accuracy is None for a
    category with zero evaluated cases (cannot occur here, but kept safe).
    """
    groups: dict[str, list] = defaultdict(list)
    for p in _evaluated(predictions):
        groups[p.category].append(p)

    result: dict[str, dict] = {}
    for category, items in groups.items():
        total = len(items)
        correct = sum(
            1 for p in items if p.predicted_readiness == p.expected_readiness
        )
        result[category] = {
            "correct": correct,
            "total": total,
            "accuracy": (correct / total) if total else None,
        }
    return result

