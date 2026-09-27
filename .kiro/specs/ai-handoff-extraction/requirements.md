# Requirements Document

## Introduction

Handoff is a web app that checks whether a work request contains enough information for someone else to execute it. A deterministic domain and readiness-validation core already exists in `backend/app/domain/`: it defines the `StructuredHandoff` model and the pure function `validate_handoff`, which is the sole authority on readiness. That core is complete and tested and is not redesigned by this feature.

This feature adds an **AI extraction layer** that converts messy natural-language handoff text into the *existing* `StructuredHandoff` model. The pipeline is:

```
raw user text → AI extraction → validated StructuredHandoff → existing deterministic validate_handoff()
```

The layer's job ends the moment it produces a valid `StructuredHandoff`. It then hands that object to the existing validator; it never inspects, computes, or reports readiness.

**Central architectural principle: "AI extracts information. Deterministic code decides readiness."** The AI (and the extraction layer around it) turns unstructured text into structured, condition-tagged fields. It classifies what information is present, missing, ambiguous, or not applicable, and it may declare that two fields contradict each other. It never outputs a readiness verdict (READY / NEEDS_CLARIFICATION / NOT_READY) and never decides whether a handoff is executable. `validate_handoff` remains the single, deterministic authority for that decision. This separation is the reason the feature stays testable, debuggable, and trustworthy: the unpredictable part (AI) only observes and labels, while the decision that matters is made by pure, deterministic code.

A second principle governs extraction quality: the **no-invention rule**. The extraction layer preserves the user's information faithfully and never fabricates facts the user did not provide. If the deadline is not stated, the deadline field is `MISSING` — not guessed as "by Friday". Faithfulness is what makes downstream readiness meaningful.

This feature covers only the extraction layer, its provider abstraction, its AI output contract, its error model, its configuration, and its tests. It does not add or change API endpoints or frontend code.

## Non-Goals

The following are explicitly out of scope for this feature and MUST NOT be introduced:

- **Readiness computation in the extraction layer.** The extraction layer never decides or emits READY / NEEDS_CLARIFICATION / NOT_READY. `validate_handoff` remains the sole readiness authority.
- **Redesigning the domain core.** The existing `FieldCondition`, `HandoffFieldName`, `HandoffField`, `StructuredHandoff`, and `validate_handoff` interfaces are consumed as-is and are not modified unless a genuine interface incompatibility is discovered.
- **Restating validator internals.** The behavior of `validate_handoff` is not re-specified here; it is referenced as the existing readiness authority the extraction output feeds into.
- **API endpoints.** No HTTP routes, request/response models, or FastAPI wiring for extraction are added in this feature.
- **Frontend.** No UI, component, or client changes.
- **Advanced AI infrastructure.** No RAG, vector databases, custom ML, model fine-tuning, multi-agent systems, autonomous agents, or orchestration frameworks.
- **Persistence and access control.** No databases, storage layers, authentication, or authorization.
- **Framework-heavy abstraction.** No plugin systems, dependency-injection frameworks, or agent architectures. The provider abstraction is a single small interface, kept simple enough for a solo student to understand, debug, and maintain.
- **New heavyweight dependencies.** Reuse the existing Python 3.14 / FastAPI / Pydantic v2 stack; add only what a Gemini-based provider genuinely requires.

## Glossary

- **Extraction layer**: The whole subsystem introduced by this feature — the extraction service plus the provider abstraction and the AI output schema. It converts raw text into a `StructuredHandoff`.
- **Extraction service**: The domain-facing component that orchestrates extraction. It accepts raw handoff text, invokes an extraction provider, validates the provider's output against the AI output schema, and constructs the existing `StructuredHandoff`. It depends only on the `Extraction provider` interface and the domain model, never on a specific AI vendor.
- **Extraction provider**: A small abstraction (Protocol/interface) that conceptually accepts raw handoff text and returns raw extraction data conforming to the AI output schema. Concrete implementations include a Gemini-based provider and test fakes/mocks. The extraction service depends on this interface, not on any concrete provider.
- **Gemini provider**: The initial concrete `Extraction provider` implementation, backed by the Gemini API. Replaceable without changing the extraction service, the domain model, or the validator.
- **AI output schema / raw extraction data**: An explicit Pydantic schema describing the *provider's* structured output — the nine fields, each with a condition and a value, plus optionally declared contradictions. This schema is distinct from the domain `StructuredHandoff`; the extraction service validates raw extraction data against it before building the domain model.
- **Field condition**: One of exactly four states a field may hold, reusing the existing `FieldCondition` enum:
  - **PRESENT** (`"present"`): the field's information is clearly stated in the input.
  - **MISSING** (`"missing"`): the input does not supply the field's information (the default for unknown information).
  - **AMBIGUOUS** (`"ambiguous"`): the input supplies information for the field, but it is unclear, vague, or open to interpretation. The extracted value is retained; the condition marks it as unclear.
  - **NOT_APPLICABLE** (`"not_applicable"`): the input gives enough context to establish that the field genuinely does not apply to this task.
- **No-invention rule**: The extraction layer preserves only information the user actually provided and never fabricates values for absent facts. Absent information is `MISSING` (or, with sufficient context, `NOT_APPLICABLE`) — never a guessed value.
- **Declared contradiction**: A `(field_a, field_b)` pair (using `HandoffFieldName`) that the AI identifies as clearly conflicting. Declared contradictions populate `StructuredHandoff.contradictions`. Declaring a contradiction is an observation, not a readiness decision.
- **Extraction error types**: A closed set of explicit error types the extraction service raises instead of returning bad data or leaking provider internals. At minimum: empty input, provider failure, provider timeout/unavailable, malformed AI response, schema validation failure, and unexpected provider response.
- **Integration boundary with `validate_handoff`**: The single hand-off point where the extraction layer's responsibility ends. The extraction service produces a valid `StructuredHandoff` and passes it to the existing `validate_handoff`. Everything on the extraction side of this boundary is observation and structuring; readiness is decided only on the far side by `validate_handoff`.

## Requirements

### Requirement 1: Accept raw handoff text as input

**User Story:** As a Handoff user, I want to submit my work request as free-form natural-language text, so that I do not have to fill in a rigid structured form myself.

#### Acceptance Criteria

1. WHEN raw handoff text is submitted to the Extraction_Service, THE Extraction_Service SHALL accept the text as the sole required input for extraction.
2. IF the submitted text is empty, THEN THE Extraction_Service SHALL raise an empty-input Extraction_Error and SHALL NOT invoke an Extraction_Provider.
3. IF the submitted text contains only whitespace characters, THEN THE Extraction_Service SHALL raise an empty-input Extraction_Error and SHALL NOT invoke an Extraction_Provider.
4. WHEN the Extraction_Service raises an empty-input Extraction_Error, THE Extraction_Service SHALL NOT call validate_handoff.

### Requirement 2: Extract the nine handoff fields via an AI provider

**User Story:** As a Handoff user, I want the system to read my messy text and pull out the parts of a complete work request, so that my request can be structured without manual effort.

#### Acceptance Criteria

1. WHEN raw handoff text is accepted, THE Extraction_Service SHALL request extraction of the nine handoff fields (objective, owner, inputs, expected_output, deadline, acceptance_criteria, context, constraints, dependencies) from an Extraction_Provider.
2. THE Extraction_Service SHALL request field values from the Extraction_Provider through the Extraction_Provider interface rather than from any specific AI vendor directly.
3. WHEN the Extraction_Provider returns raw extraction data, THE Extraction_Service SHALL obtain a condition and a value for each of the nine handoff fields.

### Requirement 3: Classify every field with exactly one condition

**User Story:** As a Handoff user, I want each part of my request labeled as present, missing, ambiguous, or not applicable, so that the downstream validator can reason about my request accurately.

#### Acceptance Criteria

1. WHEN raw extraction data is produced, THE Extraction_Service SHALL assign each of the nine handoff fields exactly one FieldCondition drawn from PRESENT, MISSING, AMBIGUOUS, or NOT_APPLICABLE.
2. IF a field's condition in the raw extraction data is not one of PRESENT, MISSING, AMBIGUOUS, or NOT_APPLICABLE, THEN THE Extraction_Service SHALL raise a schema-validation Extraction_Error.
3. WHERE a field's information is clearly stated in the input, THE Extraction_Service SHALL classify that field as PRESENT.

### Requirement 4: Never invent missing information (no-invention rule)

**User Story:** As a Handoff user, I want the system to record only what I actually wrote and never make up facts I omitted, so that the readiness verdict reflects my real request.

#### Acceptance Criteria

1. WHERE the submitted text does not supply information from which a field's value can be derived, THE Extraction_Service SHALL classify that field as MISSING and SHALL NOT populate that field with a fabricated value.
2. WHEN the input text is "Fix the login bug", THE Extraction_Service SHALL classify the deadline field as MISSING and SHALL NOT record a deadline value such as "by Friday".
3. WHEN the input text is "Fix the login bug", THE Extraction_Service SHALL classify the owner field as MISSING and SHALL NOT record an owner value such as "backend developer".
4. WHERE a field is classified as MISSING, THE Extraction_Service SHALL set that field's value to None, whether the field is single-valued or list-valued.
5. THE Extraction_Service SHALL populate a field's value only with information traceable to the submitted text, and SHALL NOT introduce information from external or world knowledge.
6. WHERE a list-valued field (inputs, acceptance_criteria, constraints, dependencies) is not supplied by the submitted text, THE Extraction_Service SHALL NOT fabricate list entries for that field.

### Requirement 5: Allow absent values for missing and not-applicable fields

**User Story:** As a Handoff user, I want fields with no information to be clearly empty rather than filled with placeholders, so that empty fields are unambiguous.

#### Acceptance Criteria

1. WHERE a field is classified as MISSING, THE Extraction_Service SHALL permit that field's value to be None.
2. WHERE a field is classified as NOT_APPLICABLE, THE Extraction_Service SHALL permit that field's value to be None.
3. WHEN constructing the StructuredHandoff, THE Extraction_Service SHALL set the value to None for every field classified as MISSING or NOT_APPLICABLE that carries no retained information.

### Requirement 6: Retain the value for ambiguous information

**User Story:** As a Handoff user, I want vague statements I made to be kept and flagged as unclear rather than dropped or guessed, so that the ambiguity is visible downstream.

#### Acceptance Criteria

1. WHERE the input supplies information for a field but that information is unclear or open to interpretation, THE Extraction_Service SHALL classify the field as AMBIGUOUS and SHALL retain the extracted value.
2. WHEN the input text is "Update the dashboard soon", THE Extraction_Service SHALL classify the objective field as PRESENT or AMBIGUOUS.
3. WHEN the input text is "Update the dashboard soon", THE Extraction_Service SHALL NOT record an invented concrete deadline value.
4. WHERE a field is classified as AMBIGUOUS, THE Extraction_Service SHALL NOT set that field's value to a fabricated concrete value.

### Requirement 7: Distinguish not-applicable from missing

**User Story:** As a Handoff user, I want the system to mark a field not-applicable only when my text shows it truly does not apply, so that genuinely absent information is not disguised as intentionally excluded.

#### Acceptance Criteria

1. WHERE the input contains an explicit statement or contextual cue that a field genuinely does not apply to the task (for example, a task described as a solo effort establishing that an owner or assignee field does not apply), THE Extraction_Service SHALL classify that field as NOT_APPLICABLE.
2. IF the input provides no value for a field and contains no explicit statement or contextual cue establishing that the field does not apply, THEN THE Extraction_Service SHALL classify that field as MISSING rather than NOT_APPLICABLE.
3. IF the input omits a field value and the only basis for exclusion is inability to locate the information, THEN THE Extraction_Service SHALL classify that field as MISSING.

### Requirement 8: Produce the existing StructuredHandoff

**User Story:** As a developer, I want the extraction result to be the existing StructuredHandoff model, so that it plugs directly into the deterministic validator with no adaptation.

#### Acceptance Criteria

1. WHEN extraction and schema validation succeed, THE Extraction_Service SHALL construct an instance of the existing StructuredHandoff model.
2. WHEN constructing the StructuredHandoff, THE Extraction_Service SHALL represent the single-valued fields (objective, owner, expected_output, deadline, context) as a str value or None.
3. WHEN constructing the StructuredHandoff, THE Extraction_Service SHALL represent the list-valued fields (inputs, acceptance_criteria, constraints, dependencies) as a list of str values or None.
4. WHEN constructing the StructuredHandoff, THE Extraction_Service SHALL pair every field value with exactly one FieldCondition using the existing HandoffField model.

### Requirement 9: Support declared contradictions

**User Story:** As a Handoff user, I want the system to note when two parts of my request clearly conflict, so that the conflict is captured for the validator to act on.

#### Acceptance Criteria

1. WHEN the Extraction_Provider identifies a clear conflict between two extracted fields, THE Extraction_Service SHALL record that conflict as a (field_a, field_b) pair using HandoffFieldName values in StructuredHandoff.contradictions.
2. WHERE no clear conflict is identified between fields, THE Extraction_Service SHALL leave StructuredHandoff.contradictions empty.
3. WHEN recording a declared contradiction, THE Extraction_Service SHALL treat the contradiction as an observation and SHALL NOT derive any readiness verdict from it.
4. IF a declared contradiction references a name that is not a valid HandoffFieldName, THEN THE Extraction_Service SHALL raise a schema-validation Extraction_Error.

### Requirement 10: Enforce the AI output contract with Pydantic validation

**User Story:** As a developer, I want the raw AI output validated against an explicit schema before it becomes a domain object, so that malformed AI output can never reach the validator.

#### Acceptance Criteria

1. THE Extraction_Service SHALL define an explicit AI_Output_Schema in which each of the nine handoff fields carries a value (a string, a list of strings, or null) together with exactly one condition drawn from the defined set of field-condition values, plus an optional list of declared contradiction pairs where each pair references two of the nine fields.
2. WHEN the Extraction_Provider returns raw extraction data, THE Extraction_Service SHALL validate that data against the AI_Output_Schema using Pydantic before it constructs a StructuredHandoff.
3. IF the raw extraction data is missing a required field, supplies a field value of an unsupported type, supplies a condition outside the defined set of field-condition values, declares a contradiction pair that does not reference two of the nine fields, or otherwise violates the AI_Output_Schema, THEN THE Extraction_Service SHALL raise a schema-validation Extraction_Error whose type and reported detail identify the failure as a schema violation.
4. IF schema validation of the raw extraction data fails, THEN THE Extraction_Service SHALL NOT alter, repair, substitute, or infer any field value or condition.
5. IF schema validation of the raw extraction data fails, THEN THE Extraction_Service SHALL NOT construct a StructuredHandoff and SHALL NOT call validate_handoff.
6. WHEN the raw extraction data passes validation against the AI_Output_Schema, THE Extraction_Service SHALL construct the StructuredHandoff solely from the validated data without modifying any field value or condition.

### Requirement 11: Separate provider-specific code behind an abstraction

**User Story:** As a developer, I want AI-vendor code isolated behind a small interface, so that the domain and validator never depend on a specific AI vendor.

#### Acceptance Criteria

1. THE Extraction_Layer SHALL define an Extraction_Provider interface that conceptually accepts raw handoff text and returns raw extraction data conforming to the AI_Output_Schema.
2. THE Extraction_Service SHALL depend on the Extraction_Provider interface and SHALL NOT depend directly on a specific AI vendor library.
3. THE Extraction_Layer SHALL provide a Gemini-based Extraction_Provider as the initial concrete implementation.
4. THE Extraction_Provider interface SHALL return raw extraction data conforming to the AI_Output_Schema rather than returning a StructuredHandoff directly.

### Requirement 12: Allow future providers without domain changes

**User Story:** As a developer, I want to add a new AI provider later without touching the domain, so that switching to a local model stays low-risk.

#### Acceptance Criteria

1. WHERE a new Extraction_Provider is added that conforms to the Extraction_Provider interface, THE Extraction_Service SHALL use it without modification to the domain model or the validator.
2. THE Extraction_Layer SHALL confine AI-vendor-specific code to concrete Extraction_Provider implementations.

### Requirement 13: Be testable without real AI API calls

**User Story:** As a developer, I want to test the entire extraction pipeline without calling a real AI service, so that tests are fast, deterministic, and free.

#### Acceptance Criteria

1. THE Extraction_Layer SHALL allow the Extraction_Service to run against a fake or mock Extraction_Provider without any real AI API call.
2. THE test suite SHALL cover a clear complete handoff, an incomplete handoff, an ambiguous handoff, NOT_APPLICABLE fields, no-invention behavior, malformed provider output, invalid enum/condition values, provider failure, empty input, successful conversion to StructuredHandoff, and declared-contradiction conversion, each using a fake or mock Extraction_Provider.
3. WHEN a deterministic fake Extraction_Provider returns identical raw extraction data for identical input, THE Extraction_Service SHALL construct an equivalent StructuredHandoff each time.
4. WHEN validate_handoff is applied to the same StructuredHandoff more than once, THE validate_handoff function SHALL return an equivalent ValidationResult each time.
5. THE existing deterministic validator tests SHALL continue to pass unchanged.

### Requirement 14: Raise explicit, safe extraction errors

**User Story:** As a developer, I want a clear set of extraction error types that never leak provider internals or secrets, so that failures are safe to surface and easy to diagnose.

#### Acceptance Criteria

1. IF the input is empty or contains only whitespace characters, THEN THE Extraction_Service SHALL raise an empty-input Extraction_Error and SHALL NOT invoke the Extraction_Provider.
2. IF the Extraction_Provider fails during extraction, THEN THE Extraction_Service SHALL raise a provider-failure Extraction_Error.
3. IF the Extraction_Provider does not return a response within a configured timeout, or the provider is unavailable, THEN THE Extraction_Service SHALL raise a provider-timeout-or-unavailable Extraction_Error.
4. IF the Extraction_Provider returns a malformed AI response, THEN THE Extraction_Service SHALL raise a malformed-AI-response Extraction_Error.
5. IF the raw extraction data fails schema validation, THEN THE Extraction_Service SHALL raise a schema-validation Extraction_Error.
6. IF the Extraction_Provider returns a response of an unexpected shape, THEN THE Extraction_Service SHALL raise an unexpected-provider-response Extraction_Error.
7. WHEN the Extraction_Service raises any Extraction_Error, THE Extraction_Service SHALL NOT expose raw provider exception details, including provider exception type, message text, or stack trace, to the caller.
8. WHEN the Extraction_Service raises any Extraction_Error, THE Extraction_Service SHALL NOT include API credentials in the error message.
9. WHEN the Extraction_Service logs a failure, THE Extraction_Service SHALL NOT write API credentials or raw provider exception details to the log output.
10. WHEN the Extraction_Service raises any Extraction_Error, THE Extraction_Service SHALL assign exactly one error type from the closed set {empty-input, provider-failure, provider-timeout-or-unavailable, malformed-AI-response, schema-validation, unexpected-provider-response} that is programmatically distinguishable by the caller.

### Requirement 15: Read configuration from the environment

**User Story:** As a developer, I want AI credentials and settings supplied through environment configuration, so that no secret is ever hard-coded.

#### Acceptance Criteria

1. THE Gemini Extraction_Provider SHALL read its API credentials from environment configuration.
2. THE Extraction_Layer SHALL NOT hard-code API credentials in source code.
3. THE feature SHALL update .env.example to list required configuration names only, including GEMINI_API_KEY and any model or timeout setting names.
4. THE .env.example file SHALL NOT contain real credential values.

### Requirement 16: Never compute readiness in the extraction layer

**User Story:** As a developer, I want a hard boundary preventing the extraction layer from judging readiness, so that "AI extracts information, deterministic code decides readiness" is enforced structurally.

#### Acceptance Criteria

1. THE Extraction_Layer SHALL NOT output any ReadinessState value (READY, NEEDS_CLARIFICATION, or NOT_READY).
2. THE Extraction_Layer SHALL NOT compute or infer a readiness verdict.
3. WHEN extraction succeeds, THE Extraction_Service SHALL produce a StructuredHandoff as its final result and SHALL delegate the readiness decision to the existing validate_handoff function.
4. THE Extraction_Layer SHALL treat validate_handoff as the sole authority for readiness at the integration boundary.
