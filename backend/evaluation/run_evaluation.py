"""Evaluation runner: run the seed dataset through the REAL Handoff pipeline.

Invoke explicitly (never at app startup):

    cd backend
    python -m evaluation.run_evaluation                 # summary only
    python -m evaluation.run_evaluation --write-results  # + evaluation-results.json
    python -m evaluation.run_evaluation --diagnostic     # + evaluation-diagnostics.json

It loads ``handoff_cases.json``, structurally validates it, runs each request
through the production ``AnalysisService`` (real Gemini extraction +
deterministic validation) built by the app's own dependency factory, compares
predictions to the manually labeled ground truth using ``metrics.py``, prints a
concise summary, and optionally writes ``evaluation-results.json``.

Diagnostic mode (``--diagnostic``) additionally serializes, for every
successfully evaluated case, the FULL real domain objects (StructuredHandoff +
ValidationResult) for human investigation, and writes them to
``evaluation-diagnostics.json``. It uses the same real pipeline and never
duplicates extraction or validation logic.

No business logic is duplicated here: readiness and issues come entirely from
the real pipeline. Configuration (API key, model) comes solely from the existing
backend config/.env - this module never reads or writes secrets, headers, or
raw provider responses.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.domain import (
    HandoffFieldName,
    ReadinessState,
    StructuredHandoff,
    ValidationResult,
)
from evaluation import metrics
from evaluation.metrics import CasePrediction

DATASET_PATH = Path(__file__).with_name("handoff_cases.json")
RESULTS_PATH = Path(__file__).with_name("evaluation-results.json")
DIAGNOSTICS_PATH = Path(__file__).with_name("evaluation-diagnostics.json")
EVALUATION_VERSION = 1

_VALID_READINESS = {s.value for s in ReadinessState}
_VALID_FIELDS = {f.value for f in HandoffFieldName}
_REQUIRED_KEYS = ("id", "category", "request", "expected_readiness")


class DatasetError(ValueError):
    """Raised when the dataset is structurally invalid."""


# --- Dataset loading + validation -------------------------------------------


def load_dataset(path: Path = DATASET_PATH) -> dict:
    """Load and structurally validate the dataset JSON, returning the dict."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    validate_dataset(data)
    return data


def validate_dataset(data: dict) -> None:
    """Validate dataset structure against the existing domain vocabulary.

    Checks: top-level shape; unique non-empty ids; non-empty category/request;
    readiness values drawn from ReadinessState; expected_critical_fields (when
    present) drawn from HandoffFieldName. Raises DatasetError on the first
    problem found. Pure - no I/O, no pipeline calls.
    """
    if not isinstance(data, dict):
        raise DatasetError("Dataset root must be a JSON object")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise DatasetError("Dataset must contain a non-empty 'cases' array")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        where = f"case #{index}"
        if not isinstance(case, dict):
            raise DatasetError(f"{where}: each case must be an object")

        for key in _REQUIRED_KEYS:
            if key not in case:
                raise DatasetError(f"{where}: missing required key '{key}'")

        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise DatasetError(f"{where}: 'id' must be a non-empty string")
        if case_id in seen_ids:
            raise DatasetError(f"{where}: duplicate id '{case_id}'")
        seen_ids.add(case_id)

        if not isinstance(case["category"], str) or not case["category"].strip():
            raise DatasetError(f"{case_id}: 'category' must be non-empty")
        if not isinstance(case["request"], str) or not case["request"].strip():
            raise DatasetError(f"{case_id}: 'request' must be non-empty")

        readiness = case["expected_readiness"]
        if readiness not in _VALID_READINESS:
            raise DatasetError(
                f"{case_id}: expected_readiness '{readiness}' is not one of "
                f"{sorted(_VALID_READINESS)}"
            )

        crit = case.get("expected_critical_fields", [])
        if not isinstance(crit, list):
            raise DatasetError(
                f"{case_id}: expected_critical_fields must be an array"
            )
        for field_name in crit:
            if field_name not in _VALID_FIELDS:
                raise DatasetError(
                    f"{case_id}: expected critical field '{field_name}' is not "
                    f"a valid Handoff field name {sorted(_VALID_FIELDS)}"
                )


# --- Running the real pipeline ----------------------------------------------


def run_cases(cases, analysis_service, capture_handoff: bool = False) -> list[CasePrediction]:
    """Run each case through the real analysis service, collecting predictions.

    An individual case failure (API/config/runtime) is recorded as an error on
    that CasePrediction and evaluation continues with the remaining cases; it is
    never treated as a model failure.

    When ``capture_handoff`` is True the raw StructuredHandoff is retained on the
    prediction (used only by diagnostic mode). This does not change any metric or
    the normal results output.
    """
    predictions: list[CasePrediction] = []
    for case in cases:
        expected_readiness = ReadinessState(case["expected_readiness"])
        expected_critical = tuple(case.get("expected_critical_fields", []))
        try:
            handoff, result = analysis_service.analyze(case["request"])
            predictions.append(
                CasePrediction(
                    id=case["id"],
                    category=case["category"],
                    expected_readiness=expected_readiness,
                    expected_critical_fields=expected_critical,
                    predicted_readiness=result.readiness_state,
                    predicted_issues=tuple(result.issues),
                    predicted_handoff=handoff if capture_handoff else None,
                )
            )
        except Exception as exc:  # infrastructure error, not a model verdict
            predictions.append(
                CasePrediction(
                    id=case["id"],
                    category=case["category"],
                    expected_readiness=expected_readiness,
                    expected_critical_fields=expected_critical,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return predictions


# --- Result assembly + reporting --------------------------------------------


def build_results(predictions, dataset_version, model) -> dict:
    """Assemble the machine-readable results structure from predictions."""
    evaluated = [p for p in predictions if p.evaluated]
    errors = [p for p in predictions if not p.evaluated]

    acc = metrics.readiness_accuracy(predictions)
    fpr = metrics.false_positive_rate(predictions)
    crit = metrics.critical_issue_detection(predictions)

    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset_version": dataset_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "summary": {
            "total_cases": len(predictions),
            "evaluated_cases": len(evaluated),
            "errors": len(errors),
            "readiness_accuracy": acc["accuracy"],
            "false_positive_rate": fpr["false_positive_rate"],
            "false_negative_count": metrics.false_negative_count(predictions),
            "critical_detection_rate": crit["critical_detection_rate"],
        },
        "category_breakdown": metrics.category_breakdown(predictions),
        "cases": [
            {
                "id": p.id,
                "category": p.category,
                "expected_readiness": p.expected_readiness.value,
                "predicted_readiness": (
                    p.predicted_readiness.value
                    if p.predicted_readiness is not None
                    else None
                ),
                "readiness_correct": (
                    p.predicted_readiness == p.expected_readiness
                    if p.evaluated
                    else None
                ),
                "expected_critical_fields": list(p.expected_critical_fields),
                "detected_critical_fields": (
                    metrics.detected_critical_fields(p) if p.evaluated else []
                ),
                "error": p.error,
            }
            for p in predictions
        ],
    }


# --- Diagnostic serialization (real domain objects only) --------------------


def serialize_handoff(handoff: StructuredHandoff) -> dict:
    """Serialize the real StructuredHandoff verbatim for human investigation.

    Iterates the nine fields in the domain's canonical HandoffFieldName order and
    copies each field's condition/value straight from the object. Contradictions
    are the declared (field_a, field_b) pairs already present on the model. No
    inference, no logic duplication, and nothing beyond the domain object (no
    secrets, headers, or raw provider payloads).
    """
    fields = {}
    for name in HandoffFieldName:
        field = getattr(handoff, name.value)
        fields[name.value] = {
            "condition": field.condition.value,
            "value": field.value,
        }
    return {
        "fields": fields,
        "contradictions": [
            [a.value, b.value] for a, b in handoff.contradictions
        ],
    }


def serialize_validation(validation: ValidationResult) -> dict:
    """Serialize the real ValidationResult verbatim (readiness + every issue)."""
    return {
        "readiness_state": validation.readiness_state.value,
        "issues": [
            {
                "issue_type": issue.issue_type.value,
                "severity": issue.severity.value,
                "field": issue.field.value,
                "secondary_field": (
                    issue.secondary_field.value
                    if issue.secondary_field is not None
                    else None
                ),
                "message": issue.explanation,
            }
            for issue in validation.issues
        ],
    }


def build_diagnostics(predictions, dataset_version, model, cases_by_id) -> dict:
    """Assemble the human-investigation diagnostic structure.

    For every successfully evaluated case, includes the full extraction and
    validation (real domain objects). Errored cases are recorded with their
    error and NO fabricated extraction/validation.
    """
    diagnostic_cases = []
    for p in predictions:
        case_meta = cases_by_id.get(p.id, {})
        entry = {
            "id": p.id,
            "category": p.category,
            "request": case_meta.get("request"),
            "expected_readiness": p.expected_readiness.value,
            "expected_critical_fields": list(p.expected_critical_fields),
            "error": p.error,
        }
        if p.evaluated:
            entry["predicted_readiness"] = p.predicted_readiness.value
            entry["readiness_correct"] = (
                p.predicted_readiness == p.expected_readiness
            )
            entry["extraction"] = (
                serialize_handoff(p.predicted_handoff)
                if p.predicted_handoff is not None
                else None
            )
            entry["validation"] = serialize_validation(
                ValidationResult(
                    readiness_state=p.predicted_readiness,
                    issues=list(p.predicted_issues),
                )
            )
        else:
            # No fabricated extraction/validation for errored cases.
            entry["predicted_readiness"] = None
            entry["readiness_correct"] = None
            entry["extraction"] = None
            entry["validation"] = None
        diagnostic_cases.append(entry)

    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset_version": dataset_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "note": (
            "Diagnostic output is for human investigation only. It is NOT "
            "automatically generated ground truth and must not be used to label "
            "the dataset."
        ),
        "cases": diagnostic_cases,
    }


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def format_summary(results: dict, dataset_name: str) -> str:
    """Render the concise human-readable CLI summary."""
    s = results["summary"]
    lines = [
        "Handoff Evaluation",
        "==================",
        "",
        f"Dataset: {dataset_name}",
        f"Cases: {s['total_cases']}",
        f"Evaluated: {s['evaluated_cases']}",
        f"Errors: {s['errors']}",
        f"Model: {results['model']}",
        "",
        f"Readiness accuracy: {_pct(s['readiness_accuracy'])}",
        f"Critical issue detection: {_pct(s['critical_detection_rate'])}",
        f"False positive rate: {_pct(s['false_positive_rate'])}",
        f"False negatives: {s['false_negative_count']}",
        "",
        "By category:",
    ]
    for category, stats in sorted(results["category_breakdown"].items()):
        lines.append(f"  {category + ':':<16} {_pct(stats['accuracy'])}")
    lines.append("")
    lines.append("Detailed results:")
    for case in results["cases"]:
        if case["error"] is not None:
            status = "ERROR"
        elif case["readiness_correct"]:
            status = "PASS"
        else:
            status = "FAIL"
        lines.append(f"  {case['id']:<10} {status}")
    return "\n".join(lines)


# --- CLI --------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Handoff evaluation dataset through the real pipeline."
    )
    parser.add_argument(
        "--write-results",
        action="store_true",
        help="Write machine-readable results to evaluation-results.json",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help=(
            "Also serialize full extraction + validation per case for human "
            "investigation and write evaluation-diagnostics.json"
        ),
    )
    args = parser.parse_args(argv)

    data = load_dataset()

    # Reuse the app's own production factory + configuration. Imported lazily so
    # merely importing this module never requires Gemini config.
    from app.api.dependencies import get_analysis_service
    from app.extraction.config import DEFAULT_MODEL, ENV_MODEL

    analysis_service = get_analysis_service()
    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL)

    predictions = run_cases(
        data["cases"], analysis_service, capture_handoff=args.diagnostic
    )
    results = build_results(predictions, data.get("version"), model)

    print(format_summary(results, DATASET_PATH.name))

    if args.write_results:
        with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"\nWrote {RESULTS_PATH.name}")

    if args.diagnostic:
        cases_by_id = {c["id"]: c for c in data["cases"]}
        diagnostics = build_diagnostics(
            predictions, data.get("version"), model, cases_by_id
        )
        with open(DIAGNOSTICS_PATH, "w", encoding="utf-8") as fh:
            json.dump(diagnostics, fh, indent=2)
        print(f"Wrote {DIAGNOSTICS_PATH.name} (for human investigation only)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())