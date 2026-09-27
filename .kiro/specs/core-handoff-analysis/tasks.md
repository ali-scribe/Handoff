# Implementation Plan: Core Handoff Analysis & Readiness Validation

## Overview

Build the AI-independent core of Handoff as a small library inside the existing `backend/app` package: a typed **Structured Handoff domain model** and a pure **deterministic Readiness Validator**. Work proceeds strictly **model-first, then validator**: the domain model (`HandoffField`, `StructuredHandoff`) is implemented and fully tested before any validator logic is written. Tests are standard Pytest (with `@pytest.mark.parametrize` where useful), run offline with the existing setup — no new dependencies, no Hypothesis/PBT, no endpoint, no frontend, no AI, no DB, no auth.

All source lives under `backend/app/domain/`; all tests under `backend/tests/domain/`.

## Tasks

- [x] 1. Set up the domain package skeleton
  - [x] 1.1 Create source and test package structure
    - Create `backend/app/domain/__init__.py` (initially empty; public API re-exports added later).
    - Create empty modules `backend/app/domain/handoff.py`, `backend/app/domain/validation.py`, `backend/app/domain/validator.py` with a module docstring each.
    - Create `backend/tests/domain/__init__.py` (project uses package-style tests) and empty `backend/tests/domain/test_handoff_model.py`, `backend/tests/domain/test_validator.py`.
    - _Requirements: 8.1, 8.2_

- [x] 2. Implement the domain model (MODEL FIRST)
  - [x] 2.1 Implement field enums and `HandoffField` in `app/domain/handoff.py`
    - Define `FieldCondition(str, Enum)` with exactly the four members `PRESENT`, `MISSING`, `AMBIGUOUS`, `NOT_APPLICABLE` (design: Enums).
    - Define `HandoffFieldName(str, Enum)` with exactly the nine members `objective`, `owner`, `inputs`, `expected_output`, `deadline`, `acceptance_criteria`, `context`, `constraints`, `dependencies` (design: Enums).
    - Define `HandoffField(BaseModel)` with `value: str | list[str] | None = None` and a required (no-default) `condition: FieldCondition`; `model_config = ConfigDict(frozen=True)` (design: `HandoffField`).
    - _Requirements: 1.2, 2.1, 2.2, 2.7_

  - [x] 2.2 Implement `StructuredHandoff` in `app/domain/handoff.py`
    - Nine required `HandoffField` fields in the design's order: `objective`, `owner`, `inputs`, `expected_output`, `deadline`, `acceptance_criteria`, `context`, `constraints`, `dependencies`.
    - Optional `contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] = []` for declared contradictions.
    - `model_config = ConfigDict(frozen=True)` (design: `StructuredHandoff`).
    - _Requirements: 1.1, 1.3, 1.7, 4.8_

  - [x]* 2.3 Write model tests in `tests/domain/test_handoff_model.py`
    - Construction succeeds for valid `value`+`condition` combinations; reading a `HandoffField` back yields the identical value and condition (never invents/alters — Req 1.4, 2.7).
    - Construction raises Pydantic `ValidationError` and produces no instance for: an invalid `FieldCondition`, a wrong `value` type; and an omitted condition — parametrized one case per field of `StructuredHandoff` (Req 1.5, 1.6).
    - Enum shape: `FieldCondition` has exactly four members, `HandoffFieldName` exactly nine (Req 2.1, 1.1).
    - `MISSING` and `NOT_APPLICABLE` are distinct enum members and both storable with `value=None` (Req 2.4, 2.6).
    - Run `pytest`; all pass.
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 2.1, 2.4, 2.6, 2.7_

- [x] 3. Model checkpoint
  - Ensure all model tests pass, ask the user if questions arise.

- [x] 4. Implement validation result models (still no validator logic)
  - [x] 4.1 Implement result enums and models in `app/domain/validation.py`
    - Define `ReadinessState(str, Enum)` with `READY`, `NEEDS_CLARIFICATION`, `NOT_READY` (Req 3.1).
    - Define `IssueSeverity(str, Enum)` with `CRITICAL`, `IMPORTANT`, `MINOR` (Req 5.1).
    - Define `IssueType(str, Enum)` with the ten members from the design (missing_objective, vague_objective, missing_required_input, missing_expected_output, vague_deadline, missing_acceptance_criteria, unresolved_dependency, contradictory_information, ambiguous_ownership, vague_action_language).
    - Define `Issue(BaseModel)`: `issue_type: IssueType`, `severity: IssueSeverity`, `field: HandoffFieldName`, `secondary_field: HandoffFieldName | None = None`, `explanation: str` (Req 6.3, 4.8).
    - Define `ValidationResult(BaseModel)`: `readiness_state: ReadinessState`, `issues: list[Issue]` (Req 6.1, 6.2, 6.5).
    - _Requirements: 3.1, 5.1, 6.1, 6.2, 6.3, 6.5_

  - [x] 4.2 Re-export the public API from `app/domain/__init__.py`
    - Re-export the enums and models (`FieldCondition`, `HandoffFieldName`, `HandoffField`, `StructuredHandoff`, `ReadinessState`, `IssueSeverity`, `IssueType`, `Issue`, `ValidationResult`) so consumers/tests import from `app.domain` (design: Module layout).
    - _Requirements: 8.1, 8.4_

- [x] 5. Implement the deterministic validator (VALIDATOR SECOND)
  - [x] 5.1 Implement the required-fields policy in `app/domain/validator.py`
    - Add a pure helper that decides requiredness per the design's policy table: `objective` and `expected_output` always required; `inputs`, `owner`, `acceptance_criteria`, `dependencies` required unless `NOT_APPLICABLE`; `deadline`, `context`, `constraints` never required.
    - Encode the two false-positive guards at the policy level: a `NOT_APPLICABLE` field is never treated as required (Req 4.11); a non-required `MISSING` field never yields a `CRITICAL` (Req 4.12).
    - _Requirements: 4.11, 4.12_

  - [x] 5.2 Implement issue detection in `validate_handoff(handoff: StructuredHandoff) -> ValidationResult`
    - Apply the ten issue-detection rules from the design table, each firing exactly one `Issue` with the mapped `IssueType` and `IssueSeverity`:
      - objective MISSING → missing_objective/CRITICAL (4.1); objective AMBIGUOUS → vague_objective/IMPORTANT (4.2).
      - inputs MISSING and required → missing_required_input/CRITICAL (4.3).
      - expected_output MISSING → missing_expected_output/CRITICAL (4.4).
      - deadline AMBIGUOUS → vague_deadline/IMPORTANT (4.5).
      - acceptance_criteria MISSING and required → missing_acceptance_criteria/IMPORTANT (4.6).
      - dependencies MISSING or AMBIGUOUS and required → unresolved_dependency/IMPORTANT (4.7).
      - owner MISSING or AMBIGUOUS and required → ambiguous_ownership/IMPORTANT (4.9).
      - objective or expected_output AMBIGUOUS → vague_action_language/MINOR (4.10), which may co-fire with rule 2 on objective.
    - Give each `Issue` a non-empty human-readable `explanation` (Req 6.3), and apply severities per Req 5.2–5.4.
    - Rules 3, 6, 7, 9 fire only when the field is required per the 5.1 policy.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.9, 4.10, 5.2, 5.3, 5.4, 6.3_

  - [x] 5.3 Implement declared-contradiction handling in `validate_handoff`
    - For each `(field_a, field_b)` pair in `handoff.contradictions`, emit exactly one `contradictory_information` issue (CRITICAL) with `field=field_a` and `secondary_field=field_b` (design: Contradiction detection).
    - _Requirements: 4.8, 5.2_

  - [x] 5.4 Implement readiness derivation in `validate_handoff`
    - Reduce the issue list: any `CRITICAL` → `NOT_READY`; else any `IMPORTANT` → `NEEDS_CLARIFICATION`; else (only `MINOR`, or empty) → `READY`.
    - Ensure the function is pure and idempotent (no I/O, no AI, no network); identical input yields an equal `ValidationResult` (Req 3.7, 4.13, 3.8).
    - Return a `ValidationResult` carrying the readiness state and the full issue list.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.13, 5.5_

- [x] 6. Validator behavior tests
  - [x]* 6.1 Write core validator tests in `tests/domain/test_validator.py`
    - One parametrized test over the ten issue-detection rows asserting each triggering `(field, condition)` produces the expected `(IssueType, field, IssueSeverity)` exactly once (Req 4.1–4.10, 5.2–5.4).
    - One parametrized test over the readiness reduction: any CRITICAL → NOT_READY; else any IMPORTANT → NEEDS_CLARIFICATION; else READY; empty → READY (Req 3.3–3.6, 5.5).
    - Two false-positive guard tests: a `NOT_APPLICABLE` field yields no missing-information issue (Req 4.11, 7.10); a non-required `MISSING` field yields no `CRITICAL` (Req 4.12).
    - Idempotence: validating the same handoff twice yields two equal `ValidationResult`s — direct assert-equal (Req 3.7, 4.13).
    - Declared contradiction: a handoff with a declared pair yields exactly one CRITICAL `contradictory_information` issue whose `field`/`secondary_field` are the two fields (Req 4.8, 5.2).
    - Issue structure: every produced issue has a valid severity, an associated field, and a non-empty explanation (Req 5.1, 6.3).
    - Empty issue list → `READY` with an empty `issues` list (Req 3.6, 6.4).
    - Run `pytest`; all pass.
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 5.1, 5.2, 5.3, 5.4, 5.5, 6.3, 6.4, 7.1, 7.2_

  - [x]* 6.2 Write the seven worked-example scenario tests in `tests/domain/test_validator.py`
    - Example 1 → READY (Req 7.3); Example 2 → NOT_READY (Req 7.4); Example 3 → NEEDS_CLARIFICATION (Req 7.5); Example 4 vague software request (Req 7.6, shows rules 2 & 10 co-firing); Example 5 university assignment with `owner`/`dependencies` = NOT_APPLICABLE producing no issues (Req 7.7, 7.10); Example 6 small-business task with NOT_APPLICABLE guards (Req 7.8, 7.10); Example 7 declared contradiction → NOT_READY (Req 7.9).
    - Each test asserts the documented issues and readiness verdict.
    - Run `pytest`; all pass.
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

- [x] 7. Final checkpoint — full suite verification
  - Run the full backend Pytest suite (including existing `test_health.py`); confirm everything passes offline with no new dependencies.
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 7.1, 8.1, 8.2, 8.3_

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Ordering is strict: the domain model (Tasks 2–3) is implemented and tested before any validator logic (Task 5).
- Each task references the specific requirement clauses it satisfies for traceability.
- Testing is standard Pytest only — no Hypothesis/PBT and no new dependencies (design: Testing Strategy).
- Checkpoints ensure incremental validation without orphaned code.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1"] },
    { "id": 5, "tasks": ["5.2"] },
    { "id": 6, "tasks": ["5.3"] },
    { "id": 7, "tasks": ["5.4"] },
    { "id": 8, "tasks": ["6.1", "6.2"] }
  ]
}
```
