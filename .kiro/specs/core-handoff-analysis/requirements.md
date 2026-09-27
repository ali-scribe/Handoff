# Requirements Document

## Introduction

Handoff is a web application that checks whether a work request contains enough information for another person to actually execute it. This feature, **Core Handoff Analysis & Readiness Validation**, covers the foundational, AI-independent core of that product: a structured domain model for a work request and a deterministic validator that decides whether the request is ready to be executed.

The product's full vision follows this workflow: a messy user work request is extracted into a structured representation, that representation is deterministically validated, missing or ambiguous information is detected, a readiness state is produced, minimal clarification questions are generated, and an improved execution-ready handoff is returned. This feature deliberately scopes only two of those stages:

1. The **Structured Handoff domain model** (the shape of the extracted representation).
2. The **deterministic Readiness Validator** (the code that decides readiness from that representation).

The central architectural principle is a strict separation of concerns: **AI extracts information into the structured representation, but deterministic application code — never AI — decides readiness.** The validator must run with no AI calls, no network, and no external services so it can be tested in isolation. AI extraction itself is explicitly out of scope for this feature; the model must be usable and testable by constructing Structured Handoff instances directly.

### Non-Goals (Explicitly Out of Scope)

The following are intentionally excluded from this feature and MUST NOT appear as in-scope requirements:

- AI / Gemini integration and any AI-based extraction behavior
- Clarification-question generation
- Frontend UI
- Database or persistence
- Authentication or authorization
- Retrieval-augmented generation (RAG), vector databases
- Custom machine learning, model fine-tuning
- Multi-agent systems
- Deployment concerns
- Unnecessary design patterns or abstractions

## Glossary

- **Handoff**: A work request expressed as structured information intended to be executed by someone other than the requester.
- **Structured_Handoff**: The Pydantic domain model representing a work request as a set of typed fields, each with an associated information condition.
- **Handoff_Field**: One conceptual slot of a Structured_Handoff. The nine fields are: objective, owner, inputs, expected_output, deadline, acceptance_criteria, context, constraints, dependencies.
- **Field_Condition**: The information state of a single Handoff_Field. Exactly one of: `PRESENT`, `MISSING`, `AMBIGUOUS`, `NOT_APPLICABLE`.
  - **PRESENT**: The field contains usable, supplied information.
  - **MISSING**: The field was not supplied and would be relevant to this task.
  - **AMBIGUOUS**: The field was supplied but is unclear, vague, or under-specified.
  - **NOT_APPLICABLE**: The field is legitimately irrelevant to this task and its absence is not a defect.
- **Readiness_State**: The overall execution-readiness verdict for a Structured_Handoff. Exactly one of: `READY`, `NEEDS_CLARIFICATION`, `NOT_READY`.
  - **READY**: The handoff contains enough clear information to be executed.
  - **NEEDS_CLARIFICATION**: The handoff is mostly complete but has one or more non-blocking questions that should be resolved.
  - **NOT_READY**: The handoff is missing or contradicts information essential to execution.
- **Readiness_Validator**: The deterministic application component that inspects a Structured_Handoff, produces a list of Issues, and derives the Readiness_State.
- **Issue**: A single detected problem with a Structured_Handoff, carrying a severity, an associated field, and a human-readable explanation.
- **Issue_Severity**: The blocking weight of an Issue. Exactly one of: `CRITICAL`, `IMPORTANT`, `MINOR`.
  - **CRITICAL**: A defect that prevents execution; drives `NOT_READY`.
  - **IMPORTANT**: A defect that should be clarified but does not by itself prevent execution; drives `NEEDS_CLARIFICATION`.
  - **MINOR**: A low-impact observation that does not block readiness.
- **Validation_Result**: The structured object returned by the Readiness_Validator, containing the Readiness_State and the list of Issues.

## Requirements

### Requirement 1: Structured Handoff Domain Model

**User Story:** As a backend developer, I want a Pydantic model representing a structured work request, so that downstream code has a well-defined, typed representation to validate.

#### Acceptance Criteria

1. THE Structured_Handoff SHALL define exactly nine fields: objective, owner, inputs, expected_output, deadline, acceptance_criteria, context, constraints, dependencies.
2. THE Structured_Handoff SHALL associate exactly one Field_Condition with each of the nine fields.
3. THE Structured_Handoff SHALL be implemented as a Pydantic model within the established `backend/app` package structure.
4. WHEN a Structured_Handoff is constructed with, for each of the nine fields, a value together with a valid Field_Condition, THE Structured_Handoff SHALL validate successfully without raising an error and SHALL expose each field's value and its associated Field_Condition.
5. IF a Structured_Handoff is constructed with a field value or Field_Condition that violates the model's type definitions, THEN THE Structured_Handoff SHALL raise a validation error and SHALL NOT produce a partially constructed instance.
6. IF a Structured_Handoff is constructed without a valid Field_Condition for any one of the nine fields, THEN THE Structured_Handoff SHALL raise a validation error.
7. THE Structured_Handoff SHALL be constructible directly in code without any AI call, network access, or external service.

### Requirement 2: Per-Field Information Conditions

**User Story:** As a backend developer, I want each field to carry an explicit information condition, so that the validator can distinguish supplied, missing, unclear, and irrelevant information without guessing.

#### Acceptance Criteria

1. THE Field_Condition SHALL be one of exactly four values: `PRESENT`, `MISSING`, `AMBIGUOUS`, `NOT_APPLICABLE`.
2. THE Structured_Handoff SHALL assign each of its nine fields exactly one Field_Condition value.
3. IF a field is supplied with a non-empty value and that value is interpretable without requiring additional clarifying input, THEN THE Structured_Handoff SHALL represent that field with the `PRESENT` condition.
4. IF a field is not supplied with any value and the field applies to the task, THEN THE Structured_Handoff SHALL represent that field with the `MISSING` condition.
5. IF a field is supplied with a value that is empty after trimming whitespace, is internally contradictory, or requires additional clarifying input to be interpreted, THEN THE Structured_Handoff SHALL represent that field with the `AMBIGUOUS` condition.
6. IF a field is not supplied with any value and the field is marked as not applying to the task, THEN THE Structured_Handoff SHALL represent that field with the `NOT_APPLICABLE` condition.
7. THE Structured_Handoff SHALL populate a field only with content that was supplied to it and SHALL NOT populate any field with content that was not supplied.

### Requirement 3: Readiness States and Deterministic Mapping

**User Story:** As a product owner, I want exactly three readiness states derived by deterministic rules, so that the readiness decision is predictable, explainable, and never made by AI.

#### Acceptance Criteria

1. THE Readiness_Validator SHALL produce exactly one Readiness_State from the set: `READY`, `NEEDS_CLARIFICATION`, `NOT_READY`.
2. THE Readiness_Validator SHALL derive the Readiness_State solely from the Structured_Handoff and its detected Issues using deterministic rules.
3. IF the detected Issues include one or more `CRITICAL` Issues, THEN THE Readiness_Validator SHALL set the Readiness_State to `NOT_READY`.
4. IF the detected Issues include no `CRITICAL` Issues and one or more `IMPORTANT` Issues, THEN THE Readiness_Validator SHALL set the Readiness_State to `NEEDS_CLARIFICATION`.
5. IF the detected Issues include no `CRITICAL` Issues and no `IMPORTANT` Issues, THEN THE Readiness_Validator SHALL set the Readiness_State to `READY`, regardless of the count of `MINOR` Issues.
6. WHILE the detected Issues set is empty, THE Readiness_Validator SHALL set the Readiness_State to `READY`.
7. WHEN the same Structured_Handoff, having identical field values and Field_Conditions, is validated two or more times, THE Readiness_Validator SHALL produce the identical Readiness_State on every validation.
8. THE Readiness_Validator SHALL determine the Readiness_State without any AI call, network access, or external service.

### Requirement 4: Deterministic Issue Detection

**User Story:** As a backend developer, I want the validator to detect specific, well-defined issue types, so that readiness problems are identified consistently and transparently.

#### Acceptance Criteria

1. IF the objective field has condition `MISSING`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates a missing objective and whose associated field is objective.
2. IF the objective field has condition `AMBIGUOUS`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates a vague objective and whose associated field is objective.
3. IF an input required for the task has condition `MISSING`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates a missing required input and whose associated field is inputs.
4. IF the expected_output field has condition `MISSING`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates a missing expected output and whose associated field is expected_output.
5. IF the deadline field has condition `AMBIGUOUS`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates a vague deadline and whose associated field is deadline.
6. IF acceptance_criteria are required for the task and have condition `MISSING`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates missing acceptance criteria and whose associated field is acceptance_criteria.
7. IF a dependency has condition `MISSING` or condition `AMBIGUOUS`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates an unresolved dependency and whose associated field is dependencies.
8. IF two fields of the Structured_Handoff hold values that cannot both be satisfied at the same time, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates contradictory information and whose associated fields are the two conflicting fields.
9. IF the owner field has condition `MISSING` or condition `AMBIGUOUS` for a task that requires an owner, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates ambiguous ownership and whose associated field is owner.
10. IF the objective field or the expected_output field has condition `AMBIGUOUS`, THEN THE Readiness_Validator SHALL record exactly one Issue whose issue type indicates vague action language and whose associated field is that field.
11. WHERE a field has condition `NOT_APPLICABLE`, THE Readiness_Validator SHALL NOT record a missing-information Issue for that field.
12. WHERE a field is not required for the task and has condition `MISSING`, THE Readiness_Validator SHALL NOT record an Issue with severity `CRITICAL` for that field solely because it is absent.
13. WHEN the Readiness_Validator evaluates a Structured_Handoff more than once with identical field values and conditions, THE Readiness_Validator SHALL record an identical set of Issues on each evaluation, with the same issue types and associated fields.

### Requirement 5: Issue Severity Classification

**User Story:** As a product owner, I want each issue classified by severity, so that only truly blocking problems prevent a handoff from being ready.

#### Acceptance Criteria

1. THE Readiness_Validator SHALL assign exactly one Issue_Severity from the set `CRITICAL`, `IMPORTANT`, `MINOR` to each detected Issue.
2. THE Readiness_Validator SHALL classify an Issue for missing information essential to execution as `CRITICAL`.
3. THE Readiness_Validator SHALL classify an Issue that should be clarified but does not prevent execution as `IMPORTANT`.
4. THE Readiness_Validator SHALL classify a low-impact observation that does not block readiness as `MINOR`.
5. THE Readiness_Validator SHALL treat `MINOR` Issues as non-blocking when deriving the Readiness_State.

### Requirement 6: Structured Validation Result

**User Story:** As a consumer of the validator, I want a structured result rather than a boolean, so that I can present the readiness verdict along with the specific issues and their explanations.

#### Acceptance Criteria

1. THE Validation_Result SHALL contain the derived Readiness_State.
2. THE Validation_Result SHALL contain the list of detected Issues.
3. THE Validation_Result SHALL represent each Issue with an Issue_Severity, an associated Handoff_Field, and a human-readable explanation.
4. WHEN no Issues are detected, THE Validation_Result SHALL contain a Readiness_State of `READY` and an empty list of Issues.
5. THE Validation_Result SHALL be implemented as a Pydantic model within the established `backend/app` package structure.

### Requirement 7: Testability Without AI or External Services

**User Story:** As a solo student developer, I want the validator to be fully testable in isolation, so that I can verify readiness logic with fast, deterministic Pytest tests.

#### Acceptance Criteria

1. THE Readiness_Validator SHALL execute using only in-memory data and deterministic logic, without any AI call, network access, or external service.
2. THE Readiness_Validator SHALL accept a Structured_Handoff constructed directly in test code as its input.
3. THE test suite SHALL include a scenario where a clearly executable handoff produces the Readiness_State `READY`.
4. THE test suite SHALL include a scenario where a handoff missing critical information produces the Readiness_State `NOT_READY`.
5. THE test suite SHALL include a scenario where a mostly complete handoff with non-blocking questions produces the Readiness_State `NEEDS_CLARIFICATION`.
6. THE test suite SHALL include a scenario for a vague software-development request.
7. THE test suite SHALL include a scenario for a university assignment task handoff.
8. THE test suite SHALL include a scenario for a small-business operational task handoff.
9. THE test suite SHALL include a scenario where a handoff containing contradictory information produces an Issue for contradictory information.
10. THE test suite SHALL include a scenario where a field with condition `NOT_APPLICABLE` produces no missing-information Issue for that field, guarding against false positives.

### Requirement 8: Engineering Simplicity Constraints

**User Story:** As a solo student developer, I want the implementation to stay simple and use the established stack, so that I can understand and maintain it without heavy infrastructure.

#### Acceptance Criteria

1. THE Structured_Handoff and Readiness_Validator SHALL be implemented in Python using Pydantic within the established FastAPI project structure.
2. THE test suite SHALL be implemented using Pytest within the `backend/tests` structure.
3. THE feature SHALL be implemented without a database, authentication, RAG, vector database, custom machine learning, model fine-tuning, or multi-agent system.
4. THE feature SHALL avoid design patterns and abstractions that are not required to satisfy these requirements.
