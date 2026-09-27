"""Evaluation runner: run the seed dataset through the REAL Handoff pipeline.

Invoke explicitly (never at app startup):

    cd backend
    python -m evaluation.run_evaluation

It loads ``handoff_cases.json``, structurally validates it, runs each request
through the production ``AnalysisService`` (real Gemini extraction +
deterministic validation) built by the app's own dependency factory, compares
predictions to the manually labeled ground truth using ``metrics.py``, prints a
concise summary, and optionally writes ``evaluation-results.json``.

No business logic is duplicated here: readiness and issues come entirely from
the real pipeline. Configuration (API key, model) comes solely from the existing
backend config/.env — this module never reads or writes secrets.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.domain import HandoffFieldName, ReadinessState
from evaluation import metrics
from evaluation.metrics import CasePrediction

DATASET_PATH = Path(__file__).with_name("handoff_cases.json")
RESULTS_PATH = Path(__file__).with_name("evaluation-results.json")
EVALUATION_VERSION = 1

_VALID_READINESS = {s.value for s in ReadinessState}
_VALID_FIELDS = {f.value for f in HandoffFieldName}
_REQUIRED_KEYS = ("id", "category", "request", "expected_readiness")


class DatasetError(ValueError):
    """Raised when the dataset is structurally invalid."""


# --- Dataset loading + validation -------------------------------------------


def load_dataset(path: Path = DATASET_PATH) -> dict:
    """Load and structurally validate the dataset JSON, returning the dict."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    validate_dataset(data)
    return data


def validate_dataset(data: dict) -> None:
    """Validate dataset structure against the existing domain vocabulary.

    Checks: top-level shape; unique non-empty ids; non-empty category/request;
    readiness values drawn from ReadinessState; expected_critical_fields (when
    present) drawn from HandoffFieldName. Raises DatasetError on the first
    problem found. Pure — no I/O, no pipeline calls.
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


def run_cases(cases, analysis_service) -> list[CasePrediction]:
    """Run each case through the real analysis service, collecting predictions.

    An individual case failure (API/config/runtime) is recorded as an error on
    that CasePrediction and evaluation continues with the remaining cases; it is
    never treated as a model failure.
    """
    predictions: list[CasePrediction] = []
    for case in cases:
        expected_readiness = ReadinessState(case["expected_readiness"])
        expected_critical = tuple(case.get("expected_critical_fields", []))
        try:
            _handoff, result = analysis_service.analyze(case["request"])
            predictions.append(
                CasePrediction(
                    id=case["id"],
                    category=case["category"],
                    expected_readiness=expected_readiness,
                    expected_critical_fields=expected_critical,
                    predicted_readiness=result.readiness_state,
                    predicted_issues=tuple(result.issues),
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
    args = parser.parse_args(argv)

    data = load_dataset()

    # Reuse the app's own production factory + configuration. Imported lazily so
    # merely importing this module never requires Gemini config.
    from app.api.dependencies import get_analysis_service
    from app.extraction.config import DEFAULT_MODEL, ENV_MODEL

    analysis_service = get_analysis_service()
    model = os.environ.get(ENV_MODEL, DEFAULT_MODEL)

    predictions = run_cases(data["cases"], analysis_service)
    results = build_results(predictions, data.get("version"), model)

    print(format_summary(results, DATASET_PATH.name))

    if args.write_results:
        with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"\nWrote {RESULTS_PATH.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
