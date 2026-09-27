/**
 * Canned API responses for tests, shaped exactly like the backend DTOs.
 * No network or AI is ever involved — tests mock the API client and use these.
 */
import type {
  AnalyzeResponse,
  ApplyAnswersResponse,
  Question,
  StructuredHandoff,
} from "../types/handoff";

/** A fully-present handoff the backend would consider READY. */
export const READY_HANDOFF: StructuredHandoff = {
  objective: { value: "Ship the quarterly report", condition: "present" },
  owner: { value: "Alice", condition: "present" },
  inputs: { value: ["data.csv", "template.docx"], condition: "present" },
  expected_output: { value: "A finished PDF report", condition: "present" },
  deadline: { value: "2025-03-01", condition: "present" },
  acceptance_criteria: { value: ["matches the template"], condition: "present" },
  context: { value: "Q1 board meeting", condition: "present" },
  constraints: { value: null, condition: "not_applicable" },
  dependencies: { value: ["service-x"], condition: "present" },
  contradictions: [],
};

/** A handoff with gaps: missing objective (critical), ambiguous deadline. */
export const NOT_READY_HANDOFF: StructuredHandoff = {
  objective: { value: null, condition: "missing" },
  owner: { value: null, condition: "missing" },
  inputs: { value: null, condition: "missing" },
  expected_output: { value: "updated code", condition: "present" },
  deadline: { value: "soon", condition: "ambiguous" },
  acceptance_criteria: { value: null, condition: "missing" },
  context: { value: null, condition: "missing" },
  constraints: { value: null, condition: "not_applicable" },
  dependencies: { value: null, condition: "not_applicable" },
  contradictions: [],
};

/** A handoff carrying a declared contradiction between deadline and dependencies. */
export const CONTRADICTION_HANDOFF: StructuredHandoff = {
  ...READY_HANDOFF,
  contradictions: [["deadline", "dependencies"]],
};

export const READY_ANALYZE_RESPONSE: AnalyzeResponse = {
  handoff: READY_HANDOFF,
  validation: { readiness_state: "ready", issues: [] },
};

export const NOT_READY_ANALYZE_RESPONSE: AnalyzeResponse = {
  handoff: NOT_READY_HANDOFF,
  validation: {
    readiness_state: "not_ready",
    issues: [
      {
        issue_type: "missing_objective",
        severity: "critical",
        field: "objective",
        secondary_field: null,
        explanation: "The objective is missing.",
      },
      {
        issue_type: "vague_deadline",
        severity: "important",
        field: "deadline",
        secondary_field: null,
        explanation: "The deadline is vague.",
      },
      {
        issue_type: "vague_action_language",
        severity: "minor",
        field: "expected_output",
        secondary_field: null,
        explanation: "The expected output uses vague action language.",
      },
    ],
  },
};

export const NEEDS_CLARIFICATION_ANALYZE_RESPONSE: AnalyzeResponse = {
  handoff: NOT_READY_HANDOFF,
  validation: {
    readiness_state: "needs_clarification",
    issues: [
      {
        issue_type: "vague_deadline",
        severity: "important",
        field: "deadline",
        secondary_field: null,
        explanation: "The deadline is vague.",
      },
    ],
  },
};

export const CONTRADICTION_ANALYZE_RESPONSE: AnalyzeResponse = {
  handoff: CONTRADICTION_HANDOFF,
  validation: {
    readiness_state: "not_ready",
    issues: [
      {
        issue_type: "contradictory_information",
        severity: "critical",
        field: "deadline",
        secondary_field: "dependencies",
        explanation:
          "The 'deadline' and 'dependencies' fields contain contradictory information.",
      },
    ],
  },
};

/** Questions the backend clarify endpoint would return for the gaps above. */
export const SAMPLE_QUESTIONS: Question[] = [
  {
    field: "objective",
    secondary_field: null,
    issue_types: ["missing_objective"],
    text: "What is the objective of this work? Describe the goal to be achieved.",
  },
  {
    field: "deadline",
    secondary_field: null,
    issue_types: ["vague_deadline"],
    text: "When is this due? Please give a specific date or time.",
  },
];

export const CONTRADICTION_QUESTION: Question = {
  field: "deadline",
  secondary_field: "dependencies",
  issue_types: ["contradictory_information"],
  text: "The 'deadline' and 'dependencies' fields appear to conflict. Which is correct?",
};

/** apply-answers response where everything is now READY. */
export const APPLIED_READY_RESPONSE: ApplyAnswersResponse = {
  handoff: READY_HANDOFF,
  validation: { readiness_state: "ready", issues: [] },
};

/**
 * A handoff the backend considers READY even though some OPTIONAL fields are
 * MISSING. Mirrors the live-QA scenario: context and constraints came back
 * missing but the backend raised no issues for them, so readiness is "ready".
 * Used to verify optional-missing fields are presented neutrally, not as errors.
 */
export const READY_WITH_OPTIONAL_MISSING_HANDOFF: StructuredHandoff = {
  objective: { value: "Fix the login bug", condition: "present" },
  owner: { value: "Alice Chen", condition: "present" },
  inputs: { value: ["auth-service repo access"], condition: "present" },
  expected_output: { value: "Updated code", condition: "present" },
  deadline: { value: null, condition: "missing" },
  acceptance_criteria: { value: ["login works on mobile"], condition: "present" },
  context: { value: null, condition: "missing" },
  constraints: { value: null, condition: "missing" },
  dependencies: { value: ["none"], condition: "present" },
  contradictions: [],
};

export const READY_WITH_OPTIONAL_MISSING_RESPONSE: AnalyzeResponse = {
  handoff: READY_WITH_OPTIONAL_MISSING_HANDOFF,
  validation: { readiness_state: "ready", issues: [] },
};
