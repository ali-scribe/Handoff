import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import IssueList from "./IssueList";
import type { Issue } from "../types/handoff";

const ISSUES: Issue[] = [
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
];

describe("IssueList", () => {
  it("shows a friendly empty state when there are no issues", () => {
    render(<IssueList issues={[]} />);
    expect(screen.getByText(/no issues found/i)).toBeInTheDocument();
  });

  it("groups issues under Critical / Important / Minor headings", () => {
    render(<IssueList issues={ISSUES} />);
    expect(screen.getByRole("heading", { name: "Critical" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Important" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Minor" })).toBeInTheDocument();
  });

  it("renders each issue's explanation and affected field", () => {
    render(<IssueList issues={ISSUES} />);
    expect(screen.getByText("The objective is missing.")).toBeInTheDocument();
    expect(screen.getByText(/Field: Objective/)).toBeInTheDocument();
    expect(screen.getByText("The deadline is vague.")).toBeInTheDocument();
  });

  it("shows the severity label as a chip per issue", () => {
    render(<IssueList issues={ISSUES} />);
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("important")).toBeInTheDocument();
    expect(screen.getByText("minor")).toBeInTheDocument();
  });

  it("shows both fields for a contradiction issue", () => {
    const contradiction: Issue[] = [
      {
        issue_type: "contradictory_information",
        severity: "critical",
        field: "deadline",
        secondary_field: "dependencies",
        explanation: "Deadline conflicts with dependencies.",
      },
    ];
    render(<IssueList issues={contradiction} />);
    expect(screen.getByText(/Field: Deadline \+ Dependencies/)).toBeInTheDocument();
  });

  it("omits a severity group that has no issues", () => {
    const onlyCritical: Issue[] = [ISSUES[0]];
    render(<IssueList issues={onlyCritical} />);
    expect(screen.getByRole("heading", { name: "Critical" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Minor" })).not.toBeInTheDocument();
  });
});
