"""Dataset + runner tests (deterministic; no Gemini).

Validates the shipped seed dataset against the real domain vocabulary and
exercises the runner's case-execution and result-assembly logic with a fake
analysis service, including infrastructure-error handling.
"""

import pytest

from app.domain import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    Issue,
    IssueSeverity,
    IssueType,
    ReadinessState,
    StructuredHandoff,
    ValidationResult,
)
from evaluation import run_evaluation
from evaluation.run_evaluation import (
    DatasetError,
    build_results,
    load_dataset,
    run_cases,
    validate_dataset,
)

VALID_READINESS = {s.value for s in ReadinessState}
VALID_FIELDS = {f.value for f in HandoffFieldName}


# --- Shipped seed dataset ---------------------------------------------------


def test_seed_dataset_loads_and_validates():
    data = load_dataset()  # raises if structurally invalid
    assert data["version"] == 1
    assert isinstance(data["cases"], list)
    assert len(data["cases"]) == 8


def test_seed_cases_have_required_fields_and_valid_values():
    data = load_dataset()
    ids = set()
    for case in data["cases"]:
        for key in ("id", "category", "request", "expected_readiness"):
            assert key in case, f"{case.get('id')} missing {key}"
        assert case["id"] not in ids, "duplicate id"
        ids.add(case["id"])
        assert case["category"].strip()
        assert case["request"].strip()
        assert case["expected_readiness"] in VALID_READINESS
        for field_name in case.get("expected_critical_fields", []):
            assert field_name in VALID_FIELDS


def test_seed_dataset_ids_are_unique():
    data = load_dataset()
    ids = [c["id"] for c in data["cases"]]
    assert len(ids) == len(set(ids))


def test_seed_dataset_covers_multiple_categories_and_outcomes():
    data = load_dataset()
    categories = {c["category"] for c in data["cases"]}
    readiness = {c["expected_readiness"] for c in data["cases"]}
    assert len(categories) >= 5
    # A mixture, not all-good or all-bad.
    assert "ready" in readiness
    assert "not_ready" in readiness


# --- validate_dataset error paths -------------------------------------------


def test_validate_rejects_missing_required_key():
    with pytest.raises(DatasetError):
        validate_dataset(
            {"cases": [{"id": "a", "category": "x", "request": "y"}]}
        )


def test_validate_rejects_duplicate_ids():
    case = {
        "id": "dup",
        "category": "x",
        "request": "y",
        "expected_readiness": "ready",
    }
    with pytest.raises(DatasetError):
        validate_dataset({"cases": [case, dict(case)]})


def test_validate_rejects_invalid_readiness():
    with pytest.raises(DatasetError):
        validate_dataset(
            {
                "cases": [
                    {
                        "id": "a",
                        "category": "x",
                        "request": "y",
                        "expected_readiness": "totally_ready",
                    }
                ]
            }
        )


def test_validate_rejects_invalid_critical_field():
    with pytest.raises(DatasetError):
        validate_dataset(
            {
                "cases": [
                    {
                        "id": "a",
                        "category": "x",
                        "request": "y",
                        "expected_readiness": "not_ready",
                        "expected_critical_fields": ["not_a_real_field"],
                    }
                ]
            }
        )


def test_validate_rejects_empty_request():
    with pytest.raises(DatasetError):
        validate_dataset(
            {
                "cases": [
                    {
                        "id": "a",
                        "category": "x",
                        "request": "   ",
                        "expected_readiness": "ready",
                    }
                ]
            }
        )


def test_validate_rejects_empty_cases():
    with pytest.raises(DatasetError):
        validate_dataset({"cases": []})


# --- Runner with a fake analysis service ------------------------------------


def _ready_handoff() -> StructuredHandoff:
    def f(v, c):
        return HandoffField(value=v, condition=c)

    return StructuredHandoff(
        objective=f("Ship it", FieldCondition.PRESENT),
        owner=f("Alice", FieldCondition.PRESENT),
        inputs=f(["data.csv"], FieldCondition.PRESENT),
        expected_output=f("A PDF", FieldCondition.PRESENT),
        deadline=f("2026-01-01", FieldCondition.PRESENT),
        acceptance_criteria=f("Looks good", FieldCondition.PRESENT),
        context=f("Q3", FieldCondition.PRESENT),
        constraints=f(None, FieldCondition.NOT_APPLICABLE),
        dependencies=f(["svc"], FieldCondition.PRESENT),
    )


class FakeAnalysisService:
    """Maps request text -> canned (handoff, ValidationResult) or raises."""

    def __init__(self, responses):
        self._responses = responses

    def analyze(self, text):
        outcome = self._responses[text]
        if isinstance(outcome, Exception):
            raise outcome
        return _ready_handoff(), outcome


def test_run_cases_records_predictions_and_errors():
    cases = [
        {
            "id": "ok-ready",
            "category": "software",
            "request": "req-ready",
            "expected_readiness": "ready",
            "expected_critical_fields": [],
        },
        {
            "id": "ok-notready",
            "category": "university",
            "request": "req-notready",
            "expected_readiness": "not_ready",
            "expected_critical_fields": ["objective"],
        },
        {
            "id": "boom",
            "category": "freelance",
            "request": "req-error",
            "expected_readiness": "ready",
            "expected_critical_fields": [],
        },
    ]
    crit = Issue(
        issue_type=IssueType.MISSING_OBJECTIVE,
        severity=IssueSeverity.CRITICAL,
        field=HandoffFieldName.OBJECTIVE,
        explanation="x",
    )
    responses = {
        "req-ready": ValidationResult(
            readiness_state=ReadinessState.READY, issues=[]
        ),
        "req-notready": ValidationResult(
            readiness_state=ReadinessState.NOT_READY, issues=[crit]
        ),
        "req-error": RuntimeError("provider exploded"),
    }
    preds = run_cases(cases, FakeAnalysisService(responses))

    by_id = {p.id: p for p in preds}
    assert by_id["ok-ready"].evaluated
    assert by_id["ok-ready"].predicted_readiness == ReadinessState.READY
    assert by_id["ok-notready"].predicted_readiness == ReadinessState.NOT_READY
    # The errored case is recorded, not silently dropped, and not evaluated.
    assert by_id["boom"].evaluated is False
    assert "RuntimeError" in by_id["boom"].error


def test_build_results_shape_and_error_accounting():
    cases = [
        {
            "id": "c1",
            "category": "software",
            "request": "r1",
            "expected_readiness": "ready",
            "expected_critical_fields": [],
        },
        {
            "id": "c2",
            "category": "software",
            "request": "r2",
            "expected_readiness": "ready",
            "expected_critical_fields": [],
        },
    ]
    responses = {
        "r1": ValidationResult(readiness_state=ReadinessState.READY, issues=[]),
        "r2": RuntimeError("boom"),
    }
    preds = run_cases(cases, FakeAnalysisService(responses))
    results = build_results(preds, dataset_version=1, model="test-model")

    s = results["summary"]
    assert s["total_cases"] == 2
    assert s["evaluated_cases"] == 1
    assert s["errors"] == 1
    # Only the one evaluated (correct) case counts toward accuracy.
    assert s["readiness_accuracy"] == 1.0
    assert results["model"] == "test-model"
    assert results["evaluation_version"] == run_evaluation.EVALUATION_VERSION
    # Errored case is present with a recorded error and null prediction.
    c2 = next(c for c in results["cases"] if c["id"] == "c2")
    assert c2["error"] is not None
    assert c2["predicted_readiness"] is None


def test_format_summary_renders_key_lines():
    cases = [
        {
            "id": "c1",
            "category": "software",
            "request": "r1",
            "expected_readiness": "ready",
            "expected_critical_fields": [],
        }
    ]
    responses = {
        "r1": ValidationResult(readiness_state=ReadinessState.READY, issues=[])
    }
    preds = run_cases(cases, FakeAnalysisService(responses))
    results = build_results(preds, dataset_version=1, model="test-model")
    text = run_evaluation.format_summary(results, "handoff_cases.json")
    assert "Handoff Evaluation" in text
    assert "Readiness accuracy: 100.0%" in text
    assert "c1" in text
