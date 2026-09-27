/**
 * TypeScript mirrors of the backend API DTOs.
 *
 * These match the FastAPI wire contracts exactly (app/api/schemas.py). The
 * frontend renders these values as-is and never recomputes readiness, severity,
 * requiredness, questions, or contradictions — the backend is authoritative.
 */

export type FieldCondition =
  | "present"
  | "missing"
  | "ambiguous"
  | "not_applicable";

export type ReadinessState = "ready" | "needs_clarification" | "not_ready";

export type IssueSeverity = "critical" | "important" | "minor";

export type HandoffFieldName =
  | "objective"
  | "owner"
  | "inputs"
  | "expected_output"
  | "deadline"
  | "acceptance_criteria"
  | "context"
  | "constraints"
  | "dependencies";

export type IssueType =
  | "missing_objective"
  | "vague_objective"
  | "missing_required_input"
  | "missing_expected_output"
  | "vague_deadline"
  | "missing_acceptance_criteria"
  | "unresolved_dependency"
  | "contradictory_information"
  | "ambiguous_ownership"
  | "vague_action_language";

/** A contradiction pair references two of the nine fields, in order. */
export type ContradictionPair = [HandoffFieldName, HandoffFieldName];

export interface HandoffField {
  value: string | string[] | null;
  condition: FieldCondition;
}

export interface StructuredHandoff {
  objective: HandoffField;
  owner: HandoffField;
  inputs: HandoffField;
  expected_output: HandoffField;
  deadline: HandoffField;
  acceptance_criteria: HandoffField;
  context: HandoffField;
  constraints: HandoffField;
  dependencies: HandoffField;
  contradictions: ContradictionPair[];
}

export interface Issue {
  issue_type: IssueType;
  severity: IssueSeverity;
  field: HandoffFieldName;
  secondary_field: HandoffFieldName | null;
  explanation: string;
}

export interface ValidationResult {
  readiness_state: ReadinessState;
  issues: Issue[];
}

export interface AnalyzeResponse {
  handoff: StructuredHandoff;
  validation: ValidationResult;
}

export interface Question {
  field: HandoffFieldName;
  secondary_field: HandoffFieldName | null;
  issue_types: IssueType[];
  text: string;
}

export interface Answer {
  field: HandoffFieldName;
  value: string;
}

export interface ApplyAnswersResponse {
  handoff: StructuredHandoff;
  validation: ValidationResult;
}

/** The nine field names in the backend's canonical (domain) order. */
export const HANDOFF_FIELD_ORDER: HandoffFieldName[] = [
  "objective",
  "owner",
  "inputs",
  "expected_output",
  "deadline",
  "acceptance_criteria",
  "context",
  "constraints",
  "dependencies",
];

/** Human-readable labels for each field (display only). */
export const FIELD_LABELS: Record<HandoffFieldName, string> = {
  objective: "Objective",
  owner: "Owner",
  inputs: "Inputs",
  expected_output: "Expected output",
  deadline: "Deadline",
  acceptance_criteria: "Acceptance criteria",
  context: "Context",
  constraints: "Constraints",
  dependencies: "Dependencies",
};
