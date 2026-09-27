# Implementation Plan: AI Handoff Extraction

## Overview

This plan builds the AI extraction layer as a single new package, `backend/app/extraction/`, that turns free-form handoff text into the existing `StructuredHandoff` domain model. The layer imports from `app.domain` and never modifies it, never computes readiness, and never calls `validate_handoff` (Req 16).

The build order is inside-out: pure/leaf modules first (errors, schema, config), then the provider interface, then the orchestrating service, then the concrete Gemini provider, then the public API surface and `.env.example`, ending with a full-suite checkpoint. Each step builds on the previous one so there is no orphaned code. The Gemini REST call uses the already-present `httpx` dependency — no new dependency is added.

Testing is standard **pytest** only, using `@pytest.mark.parametrize` where useful. Property-based testing is intentionally not used (the design has no Correctness Properties section), so there are no property sub-tasks. Test-writing sub-tasks are marked optional with `*`.

## Tasks

- [ ] 1. Create the extraction package skeleton
  - Create `backend/app/extraction/__init__.py` (empty placeholder for now; public re-exports are wired in task 8).
  - Create empty modules, each with only a module docstring stating its single responsibility: `config.py`, `schema.py`, `errors.py`, `provider.py`, `gemini_provider.py`, `service.py`.
  - Create `backend/tests/extraction/__init__.py` so the test package is importable.
  - Do not modify anything under `app/domain`.
  - _Design: Module Layout_
  - _Requirements: 11, 13.1_

- [ ] 2. Implement the closed error set in `errors.py`
  - Define `ExtractionError(Exception)` as the base for every extraction error.
  - Define the closed set of subclasses exactly as in the design: `EmptyInputError`, `ProviderFailureError`, `MissingApiKeyError(ProviderFailureError)`, `ProviderTimeoutError`, `MalformedResponseError`, `SchemaValidationError`, `UnexpectedResponseError`.
  - Add `SchemaValidationError.from_pydantic(exc: ValidationError)` classmethod that builds a safe detail string from Pydantic's structured errors using error `loc` + `type` only — never raw provider text or secrets.
  - Ensure each error type is programmatically distinguishable by the caller (distinct classes; `MissingApiKeyError` is a `ProviderFailureError` subtype).
  - _Design: Error Model; "Which error for which case" table_
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.10_

- [ ] 3. Implement the AI output schema in `schema.py`
  - [ ] 3.1 Define `RawField` and `RawExtraction`
    - `RawField`: `value: str | list[str] | None = None`, `condition: FieldCondition` (required, no default), `model_config = ConfigDict(extra="forbid")`.
    - `RawExtraction`: the nine `RawField` fields in domain order (objective, owner, inputs, expected_output, deadline, acceptance_criteria, context, constraints, dependencies), plus `contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] = []`, with `model_config = ConfigDict(extra="forbid")`.
    - Import `FieldCondition` and `HandoffFieldName` from `app.domain` so out-of-vocabulary conditions and invalid field names fail Pydantic validation automatically.
    - _Design: AI output schema — schema.py; Data Models_
    - _Requirements: 3.1, 3.2, 5.1, 5.2, 6, 9.4, 10.1_

  - [ ]* 3.2 Write `test_schema.py`
    - Valid full payload passes `RawExtraction.model_validate`.
    - Each of the following raises `pydantic.ValidationError`: a missing required field, a wrong-typed value, a bad condition string (e.g. `"urgent"`), a bad contradiction field name (e.g. `"banana"`), an extra top-level key, and an extra key inside a field object.
    - Use `@pytest.mark.parametrize` across the rejection cases.
    - _Design: Schema tests (test_schema.py)_
    - _Requirements: 3.2, 9.4, 10.3_

- [ ] 4. Implement environment configuration in `config.py`
  - Define env var name constants `ENV_API_KEY = "GEMINI_API_KEY"`, `ENV_MODEL = "GEMINI_MODEL"`, `ENV_TIMEOUT = "GEMINI_TIMEOUT_SECONDS"`, plus `DEFAULT_MODEL = "gemini-2.0-flash"` and `DEFAULT_TIMEOUT_SECONDS = 30.0`.
  - Define frozen dataclass `GeminiConfig(api_key, model, timeout_seconds)`.
  - Implement `load_gemini_config()` reading `os.environ`: raise `MissingApiKeyError` (from `errors.py`) when the API key is absent; apply `DEFAULT_MODEL` and `DEFAULT_TIMEOUT_SECONDS` when unset.
  - Never log or echo the key value.
  - _Design: Configuration — config.py; Configuration (Req 15)_
  - _Requirements: 15.1, 15.2, 14.8, 14.9_

- [ ] 5. Implement the provider interface in `provider.py`
  - Define `ExtractionProvider` as a `@runtime_checkable typing.Protocol` with a single method `extract(self, text: str) -> dict`.
  - Docstring must state: implementations return a JSON-decoded dict for the service to validate; implementations raise the typed provider/timeout/malformed errors; they MUST NOT build a `StructuredHandoff` and MUST NOT compute readiness.
  - _Design: Provider interface — provider.py_
  - _Requirements: 11.1, 11.2, 11.4, 12_

- [ ] 6. Implement the extraction service in `service.py`
  - [ ] 6.1 Implement `raw_to_structured(raw: RawExtraction) -> StructuredHandoff`
    - Pure, deterministic mapping: build one `HandoffField(value=rf.value, condition=rf.condition)` per field and pass `contradictions` through as `list(raw.contradictions)`.
    - Copy values and conditions verbatim; introduce no facts and modify nothing.
    - Do not import or call `validate_handoff` / `ReadinessState`.
    - _Design: Extraction service — service.py; Mapping to StructuredHandoff_
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 10.6, 16.1, 16.2_

  - [ ] 6.2 Implement `ExtractionService(provider).extract(text)`
    - Ordered steps: (a) if text is None or whitespace-only, raise `EmptyInputError` **before** calling the provider; (b) call `provider.extract(text)` and let typed provider/timeout/malformed errors propagate; (c) if the result is not a `dict`, raise `MalformedResponseError`; (d) `RawExtraction.model_validate(...)` and on `ValidationError` raise `SchemaValidationError.from_pydantic(exc) from None`; (e) return `raw_to_structured(raw)`.
    - No repair, guessing, or field inference on failure; no `StructuredHandoff` built and no readiness computed on any failure path.
    - Depend only on the `ExtractionProvider` interface and the domain model; return type is `StructuredHandoff`.
    - _Design: Extraction service — service.py; Orchestration order; Integration Boundary_
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 10.2, 10.3, 10.4, 10.5, 16.1, 16.2, 16.3_

  - [ ]* 6.3 Write `fakes.py` test doubles
    - `FakeProvider(payload: dict)` returning a fixed dict; `SpyProvider` recording whether `extract` was called; `RaisingProvider(exc)` raising a given typed error.
    - Each implements the `ExtractionProvider` Protocol structurally (no base class needed).
    - _Design: Fakes and spies (fakes.py)_
    - _Requirements: 13.1_

  - [ ]* 6.4 Write `test_service.py` covering the design's 17-case table
    - Clear complete handoff (verbatim copy); incomplete handoff (MISSING/`None`); ambiguous handoff (value retained); NOT_APPLICABLE (`value=None`); no-invention pass-through (output equals input field-by-field, no added facts).
    - Malformed non-dict result -> `MalformedResponseError`; invalid enum/condition -> `SchemaValidationError`; invalid contradiction name -> `SchemaValidationError`; extra-key rejection -> `SchemaValidationError`.
    - Provider failure via `RaisingProvider(ProviderFailureError)` and timeout via `RaisingProvider(ProviderTimeoutError)` propagate; empty and whitespace input with `SpyProvider` raise `EmptyInputError` and assert the provider was **not** called.
    - Successful conversion returns a `StructuredHandoff`; declared-contradiction conversion passes the pair through unchanged; determinism (same payload twice yields equal `StructuredHandoff`).
    - `validate_handoff` idempotence composed **in the test** (not the service); boundary assertion that `app.extraction` imports no `validate_handoff` / `ReadinessState` and `extract` returns a `StructuredHandoff`.
    - Use `@pytest.mark.parametrize` across the incomplete/ambiguous/not-applicable field variants and the empty/whitespace variants.
    - _Design: Testing Strategy — Test cases mapped to Req 13.2_
    - _Requirements: 1.2, 1.3, 1.4, 2.3, 4.1, 4.4, 4.5, 5.1, 5.2, 6.1, 6.4, 7.1, 8.1, 9.1, 9.2, 10.3, 10.6, 13.2, 13.3, 13.4, 14.2, 14.3, 14.4, 16.1, 16.2, 16.3_

- [ ] 7. Implement the Gemini provider in `gemini_provider.py`
  - [ ] 7.1 Implement `GeminiProvider` and `_build_prompt`
    - `GeminiProvider(config: GeminiConfig | None = None)` resolving config via `load_gemini_config()` when not supplied.
    - `extract(text)` performs `httpx.post` to the REST `generateContent` endpoint with the model from config, passes the API key as a query param, decodes the model text part, and `json.loads` it into a dict.
    - Map failures with `from None` and fixed safe log strings: `httpx.TimeoutException` -> `ProviderTimeoutError`; `httpx.HTTPError` -> `ProviderFailureError`; decode/shape failure (`KeyError`/`IndexError`/`ValueError`/`TypeError`) -> `MalformedResponseError`. Never log or raise the API key or raw exception text.
    - Pure helper `_build_prompt(text)` instructs strict JSON matching the schema (nine fields, each `{value, condition}`, plus optional `contradictions`) and the no-invention / condition policy (MISSING with `value=None`, retain value for AMBIGUOUS, NOT_APPLICABLE only on a contextual cue).
    - _Design: Gemini provider — gemini_provider.py; No-Invention Guarantees_
    - _Requirements: 11.3, 14.2, 14.3, 14.4, 14.7, 14.8, 14.9, 15.1, 15.2_

  - [ ]* 7.2 Write `test_gemini_provider.py`
    - Drive exception mapping via `httpx.MockTransport`: timeout -> `ProviderTimeoutError`; non-2xx status -> `ProviderFailureError`; non-JSON / wrongly-shaped body -> `MalformedResponseError`.
    - Assert error messages contain no API key and no raw exception text.
    - Config tests: missing `GEMINI_API_KEY` -> `MissingApiKeyError`; defaults applied when `GEMINI_MODEL` / `GEMINI_TIMEOUT_SECONDS` are unset.
    - Assert `_build_prompt` output mentions the nine fields and the four conditions.
    - _Design: Gemini provider tests (test_gemini_provider.py)_
    - _Requirements: 14.2, 14.3, 14.4, 14.7, 14.8, 14.9, 15.1_

- [ ] 8. Wire the public API in `app/extraction/__init__.py`
  - Re-export `ExtractionService`, `raw_to_structured`, `ExtractionProvider`, `GeminiProvider`, `RawExtraction`, `RawField`, and all error types (`ExtractionError`, `EmptyInputError`, `ProviderFailureError`, `ProviderTimeoutError`, `MalformedResponseError`, `SchemaValidationError`, `UnexpectedResponseError`).
  - Define `__all__` listing the public surface, mirroring how `app.domain` re-exports its API.
  - _Design: Public API — __init__.py_
  - _Requirements: 11_

- [ ] 9. Update `backend/.env.example` with Gemini configuration names
  - Add `GEMINI_API_KEY`, `GEMINI_MODEL`, and `GEMINI_TIMEOUT_SECONDS` as names only, with no real values.
  - _Design: Configuration (Req 15)_
  - _Requirements: 15.3, 15.4_

- [ ] 10. Final checkpoint — full suite and boundary verification
  - Run the full backend pytest suite; confirm the new extraction tests pass and the existing 57 domain tests still pass unchanged.
  - Confirm no new dependency was added (`requirements.txt` unchanged) and that no module in `app/extraction` imports `validate_handoff`, `ValidationResult`, or `ReadinessState`.
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 13.5, 16.1, 16.2, 16.4_

## Notes

- Tasks marked with `*` are optional test-writing sub-tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references the specific requirement clauses and design sections it satisfies for traceability.
- The plan reuses `app.domain` (FieldCondition, HandoffFieldName, HandoffField, StructuredHandoff) and never modifies the domain core.
- No API endpoint, frontend, database, or auth work is included — this feature is a library layer only.
- No new dependency is introduced; the Gemini provider uses the existing `httpx>=0.28`.
- Testing is standard pytest with `parametrize`; property-based testing is intentionally not used (the design has no Correctness Properties section).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2", "5"] },
    { "id": 2, "tasks": ["3.1", "4"] },
    { "id": 3, "tasks": ["3.2", "6.1"] },
    { "id": 4, "tasks": ["6.2", "7.1"] },
    { "id": 5, "tasks": ["6.3", "9"] },
    { "id": 6, "tasks": ["6.4", "7.2", "8"] }
  ]
}
```
