"""Deterministic tests for the evaluation metrics.

These never call Gemini or the validator. They construct CasePrediction records
directly (using the real domain Issue/IssueSeverity/ReadinessState models) and
assert the pure metric math, including zero-case and division-by-zero handling.
"""

from app.domain import (
    HandoffFieldName,
    Issue,
    IssueSeverity,
    IssueType,
    ReadinessState,
)
from evaluation import metrics
from evaluation.metrics import CasePrediction

READY = ReadinessState.READY
NEEDS = ReadinessState.NEEDS_CLARIFICATION
NOT_READY = ReadinessState.NOT_READY


def _critical_issue(field: HandoffFieldName, secondary=None) -> Issue:
    return Issue(
        issue_type=IssueType.MISSING_OBJECTIVE,
        severity=IssueSeverity.CRITICAL,
        field=field,
        secondary_field=secondary,
        explanation="x",
    )


def _important_issue(field: HandoffFieldName) -> Issue:
    return Issue(
        issue_type=IssueType.VAGUE_DEADLINE,
        severity=IssueSeverity.IMPORTANT,
        field=field,
        explanation="x",
    )


def _pred(
    *,
    id="c",
    category="software",
    expected=NOT_READY,
    predicted=NOT_READY,
    expected_critical=(),
    issues=(),
    error=None,
) -> CasePrediction:
    return CasePrediction(
        id=id,
        category=category,
        expected_readiness=expected,
        expected_critical_fields=tuple(expected_critical),
        predicted_readiness=None if error else predicted,
        predicted_issues=tuple(issues),
        error=error,
    )


# --- Readiness accuracy -----------------------------------------------------


def test_readiness_accuracy_all_correct():
    preds = [
        _pred(expected=READY, predicted=READY),
        _pred(expected=NOT_READY, predicted=NOT_READY),
    ]
    result = metrics.readiness_accuracy(preds)
    assert result == {"correct": 2, "total": 2, "accuracy": 1.0}


def test_readiness_accuracy_partial():
    preds = [
        _pred(expected=READY, predicted=READY),
        _pred(expected=NOT_READY, predicted=READY),
        _pred(expected=NEEDS, predicted=NEEDS),
        _pred(expected=NOT_READY, predicted=NEEDS),
    ]
    result = metrics.readiness_accuracy(preds)
    assert result["correct"] == 2
    assert result["total"] == 4
    assert result["accuracy"] == 0.5


def test_readiness_accuracy_zero_cases_returns_none():
    result = metrics.readiness_accuracy([])
    assert result == {"correct": 0, "total": 0, "accuracy": None}


def test_readiness_accuracy_excludes_errored_cases():
    preds = [
        _pred(expected=READY, predicted=READY),
        _pred(expected=NOT_READY, error="boom"),
    ]
    result = metrics.readiness_accuracy(preds)
    # The errored case is not counted in the denominator.
    assert result == {"correct": 1, "total": 1, "accuracy": 1.0}


# --- False positives / negatives -------------------------------------------


def test_false_positive_rate():
    preds = [
        _pred(expected=READY, predicted=NOT_READY),  # false positive
        _pred(expected=READY, predicted=READY),  # ok
        _pred(expected=NOT_READY, predicted=NOT_READY),  # not a ready case
    ]
    result = metrics.false_positive_rate(preds)
    assert result["false_positive_count"] == 1
    assert result["ready_case_count"] == 2
    assert result["false_positive_rate"] == 0.5


def test_false_positive_rate_no_ready_cases_returns_none():
    preds = [_pred(expected=NOT_READY, predicted=NOT_READY)]
    result = metrics.false_positive_rate(preds)
    assert result["ready_case_count"] == 0
    assert result["false_positive_rate"] is None


def test_false_negative_count():
    preds = [
        _pred(expected=NOT_READY, predicted=READY),  # false negative
        _pred(expected=NEEDS, predicted=READY),  # false negative
        _pred(expected=NOT_READY, predicted=NOT_READY),  # ok
        _pred(expected=READY, predicted=READY),  # not a negative case
    ]
    assert metrics.false_negative_count(preds) == 2


# --- Critical detection -----------------------------------------------------


def test_critical_detection_full():
    preds = [
        _pred(
            expected_critical=[HandoffFieldName.OBJECTIVE.value],
            issues=[_critical_issue(HandoffFieldName.OBJECTIVE)],
        ),
    ]
    result = metrics.critical_issue_detection(preds)
    assert result["expected_critical_count"] == 1
    assert result["detected_critical_count"] == 1
    assert result["critical_detection_rate"] == 1.0


def test_critical_detection_partial_and_severity_matters():
    preds = [
        _pred(
            expected_critical=[
                HandoffFieldName.OBJECTIVE.value,
                HandoffFieldName.EXPECTED_OUTPUT.value,
            ],
            # objective flagged CRITICAL; expected_output only IMPORTANT ->
            # not counted as a critical detection.
            issues=[
                _critical_issue(HandoffFieldName.OBJECTIVE),
                _important_issue(HandoffFieldName.EXPECTED_OUTPUT),
            ],
        ),
    ]
    result = metrics.critical_issue_detection(preds)
    assert result["expected_critical_count"] == 2
    assert result["detected_critical_count"] == 1
    assert result["critical_detection_rate"] == 0.5


def test_critical_detection_matches_secondary_field():
    # A contradiction names two fields; either should count.
    preds = [
        _pred(
            expected_critical=[HandoffFieldName.DEPENDENCIES.value],
            issues=[
                _critical_issue(
                    HandoffFieldName.DEADLINE,
                    secondary=HandoffFieldName.DEPENDENCIES,
                )
            ],
        ),
    ]
    result = metrics.critical_issue_detection(preds)
    assert result["detected_critical_count"] == 1


def test_critical_detection_no_expected_returns_none():
    preds = [_pred(expected_critical=[], issues=[])]
    result = metrics.critical_issue_detection(preds)
    assert result["expected_critical_count"] == 0
    assert result["critical_detection_rate"] is None


def test_detected_critical_fields_lists_only_matched():
    p = _pred(
        expected_critical=[
            HandoffFieldName.OBJECTIVE.value,
            HandoffFieldName.EXPECTED_OUTPUT.value,
        ],
        issues=[_critical_issue(HandoffFieldName.OBJECTIVE)],
    )
    assert metrics.detected_critical_fields(p) == [HandoffFieldName.OBJECTIVE.value]


# --- Category breakdown -----------------------------------------------------


def test_category_breakdown():
    preds = [
        _pred(category="software", expected=READY, predicted=READY),
        _pred(category="software", expected=NOT_READY, predicted=NOT_READY),
        _pred(category="university", expected=NOT_READY, predicted=READY),
    ]
    result = metrics.category_breakdown(preds)
    assert result["software"] == {"correct": 2, "total": 2, "accuracy": 1.0}
    assert result["university"] == {"correct": 0, "total": 1, "accuracy": 0.0}


def test_category_breakdown_excludes_errors():
    preds = [
        _pred(category="software", expected=READY, predicted=READY),
        _pred(category="software", expected=NOT_READY, error="boom"),
    ]
    result = metrics.category_breakdown(preds)
    assert result["software"] == {"correct": 1, "total": 1, "accuracy": 1.0}
