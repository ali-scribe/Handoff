"""Deterministic tests for evaluation diagnostic mode (no Gemini).

Covers serialization of the real domain objects (fields/conditions/values,
validation issues + severity, contradictions), the error-case handling, and the
CLI --diagnostic behavior (using a fake analysis service, never the real API).
"""

import json

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
from evaluation.metrics import CasePrediction
from evaluation.run_evaluation import (
    build_diagnostics,
    run_cases,
    serialize_handoff,
    serialize_validation,
)


def _f(v, c):
    return HandoffField(value=v, condition=c)


def _handoff_with_contradiction() -> StructuredHandoff:
    return StructuredHandoff(
        objective=_f("Ship it", FieldCondition.PRESENT),
        owner=_f(None, FieldCondition.MISSING),
        inputs=_f(["data.csv", "template.docx"], FieldCondition.PRESENT),
        expected_output=_f("A PDF", FieldCondition.PRESENT),
        deadline=_f("soon", FieldCondition.AMBIGUOUS),
        acceptance_criteria=_f(None, FieldCondition.MISSING),
        context=_f(None, FieldCondition.NOT_APPLICABLE),
        constraints=_f(None, FieldCondition.NOT_APPLICABLE),
        dependencies=_f(["svc-x"], FieldCondition.PRESENT),
        contradictions=[(HandoffFieldName.DEADLINE, HandoffFieldName.DEPENDENCIES)],
    )


# --- serialize_handoff ------------------------------------------------------


def test_serialize_handoff_includes_all_nine_fields_with_condition_and_value():
    data = serialize_handoff(_handoff_with_contradiction())
    assert set(data["fields"].keys()) == {f.value for f in HandoffFieldName}

    assert data["fields"]["objective"] == {
        "condition": "present",
        "value": "Ship it",
    }
    # Missing field: condition preserved, value verbatim (None).
    assert data["fields"]["owner"] == {"condition": "missing", "value": None}
    # Ambiguous field keeps its extracted value.
    assert data["fields"]["deadline"] == {
        "condition": "ambiguous",
        "value": "soon",
    }
    # List value preserved as-is.
    assert data["fields"]["inputs"]["value"] == ["data.csv", "template.docx"]


def test_serialize_handoff_serializes_contradictions():
    data = serialize_handoff(_handoff_with_contradiction())
    assert data["contradictions"] == [["deadline", "dependencies"]]


def test_serialize_handoff_empty_contradictions():
    handoff = _handoff_with_contradiction().model_copy(update={"contradictions": []})
    assert serialize_handoff(handoff)["contradictions"] == []


# --- serialize_validation ---------------------------------------------------


def test_serialize_validation_readiness_and_issue_fields():
    issue = Issue(
        issue_type=IssueType.CONTRADICTORY_INFORMATION,
        severity=IssueSeverity.CRITICAL,
        field=HandoffFieldName.DEADLINE,
        secondary_field=HandoffFieldName.DEPENDENCIES,
        explanation="They conflict.",
    )
    validation = ValidationResult(
        readiness_state=ReadinessState.NOT_READY, issues=[issue]
    )
    data = serialize_validation(validation)
    assert data["readiness_state"] == "not_ready"
    assert len(data["issues"]) == 1
    got = data["issues"][0]
    assert got["issue_type"] == "contradictory_information"
    assert got["severity"] == "critical"
    assert got["field"] == "deadline"
    assert got["secondary_field"] == "dependencies"
    assert got["message"] == "They conflict."


def test_serialize_validation_issue_without_secondary_field():
    issue = Issue(
        issue_type=IssueType.MISSING_OBJECTIVE,
        severity=IssueSeverity.CRITICAL,
        field=HandoffFieldName.OBJECTIVE,
        explanation="Missing objective.",
    )
    data = serialize_validation(
        ValidationResult(readiness_state=ReadinessState.NOT_READY, issues=[issue])
    )
    assert data["issues"][0]["secondary_field"] is None


# --- build_diagnostics ------------------------------------------------------


def test_build_diagnostics_evaluated_and_error_cases():
    good = CasePrediction(
        id="c1",
        category="software",
        expected_readiness=ReadinessState.NOT_READY,
        expected_critical_fields=("objective",),
        predicted_readiness=ReadinessState.NOT_READY,
        predicted_issues=(
            Issue(
                issue_type=IssueType.MISSING_OBJECTIVE,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.OBJECTIVE,
                explanation="x",
            ),
        ),
        predicted_handoff=_handoff_with_contradiction(),
    )
    errored = CasePrediction(
        id="c2",
        category="university",
        expected_readiness=ReadinessState.READY,
        error="ProviderTimeoutError: timed out",
    )
    cases_by_id = {
        "c1": {"id": "c1", "request": "req one"},
        "c2": {"id": "c2", "request": "req two"},
    }
    diag = build_diagnostics(
        [good, errored], dataset_version=1, model="test-model", cases_by_id=cases_by_id
    )

    assert diag["model"] == "test-model"
    assert "human investigation" in diag["note"].lower()

    by_id = {c["id"]: c for c in diag["cases"]}

    c1 = by_id["c1"]
    assert c1["request"] == "req one"
    assert c1["predicted_readiness"] == "not_ready"
    assert c1["readiness_correct"] is True
    assert c1["extraction"]["fields"]["owner"]["condition"] == "missing"
    assert c1["extraction"]["contradictions"] == [["deadline", "dependencies"]]
    assert c1["validation"]["issues"][0]["severity"] == "critical"

    # Error case: recorded, with NO fabricated extraction/validation.
    c2 = by_id["c2"]
    assert c2["error"] == "ProviderTimeoutError: timed out"
    assert c2["extraction"] is None
    assert c2["validation"] is None
    assert c2["predicted_readiness"] is None


# --- CLI --diagnostic (fake analysis service) -------------------------------


class _FakeAnalysisService:
    def analyze(self, text):
        handoff = _handoff_with_contradiction()
        validation = ValidationResult(
            readiness_state=ReadinessState.NOT_READY,
            issues=[
                Issue(
                    issue_type=IssueType.MISSING_OBJECTIVE,
                    severity=IssueSeverity.CRITICAL,
                    field=HandoffFieldName.OBJECTIVE,
                    explanation="x",
                )
            ],
        )
        return handoff, validation


def test_cli_diagnostic_writes_diagnostics_file(monkeypatch, tmp_path):
    # Point output paths into a temp dir so nothing real is written.
    monkeypatch.setattr(
        run_evaluation, "DIAGNOSTICS_PATH", tmp_path / "evaluation-diagnostics.json"
    )
    monkeypatch.setattr(
        run_evaluation, "RESULTS_PATH", tmp_path / "evaluation-results.json"
    )
    # Use the fake service instead of the real Gemini-backed one.
    monkeypatch.setattr(
        "app.api.dependencies.get_analysis_service",
        lambda: _FakeAnalysisService(),
    )

    rc = run_evaluation.main(["--diagnostic"])
    assert rc == 0

    diag_file = tmp_path / "evaluation-diagnostics.json"
    assert diag_file.exists()
    # Normal results file is NOT written unless --write-results is passed.
    assert not (tmp_path / "evaluation-results.json").exists()

    diag = json.loads(diag_file.read_text(encoding="utf-8"))
    assert diag["cases"], "diagnostics should contain cases"
    first = diag["cases"][0]
    assert "extraction" in first and "validation" in first
    assert first["extraction"]["fields"]["objective"]["condition"] == "present"


def test_cli_normal_run_does_not_write_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_evaluation, "DIAGNOSTICS_PATH", tmp_path / "evaluation-diagnostics.json"
    )
    monkeypatch.setattr(
        run_evaluation, "RESULTS_PATH", tmp_path / "evaluation-results.json"
    )
    monkeypatch.setattr(
        "app.api.dependencies.get_analysis_service",
        lambda: _FakeAnalysisService(),
    )

    rc = run_evaluation.main([])
    assert rc == 0
    assert not (tmp_path / "evaluation-diagnostics.json").exists()
    assert not (tmp_path / "evaluation-results.json").exists()


def test_cli_diagnostic_does_not_leak_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_evaluation, "DIAGNOSTICS_PATH", tmp_path / "evaluation-diagnostics.json"
    )
    monkeypatch.setattr(
        "app.api.dependencies.get_analysis_service",
        lambda: _FakeAnalysisService(),
    )
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-VALUE-123")

    run_evaluation.main(["--diagnostic"])
    text = (tmp_path / "evaluation-diagnostics.json").read_text(encoding="utf-8")
    assert "SECRET-KEY-VALUE-123" not in text
    assert "GEMINI_API_KEY" not in text