import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StructuredFields from "./StructuredFields";
import {
  NOT_READY_ANALYZE_RESPONSE,
  NOT_READY_HANDOFF,
  READY_HANDOFF,
  READY_WITH_OPTIONAL_MISSING_HANDOFF,
} from "../test/fixtures";
import type { ValidationResult } from "../types/handoff";

const NO_ISSUES: ValidationResult = { readiness_state: "ready", issues: [] };

describe("StructuredFields", () => {
  it("renders all nine fields with their labels", () => {
    render(<StructuredFields handoff={READY_HANDOFF} validation={NO_ISSUES} />);
    for (const label of [
      "Objective",
      "Owner",
      "Inputs",
      "Expected output",
      "Deadline",
      "Acceptance criteria",
      "Context",
      "Constraints",
      "Dependencies",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("shows a present scalar value", () => {
    render(<StructuredFields handoff={READY_HANDOFF} validation={NO_ISSUES} />);
    expect(screen.getByText("Ship the quarterly report")).toBeInTheDocument();
  });

  it("renders a present list value as list items", () => {
    render(<StructuredFields handoff={READY_HANDOFF} validation={NO_ISSUES} />);
    expect(screen.getByText("data.csv")).toBeInTheDocument();
    expect(screen.getByText("template.docx")).toBeInTheDocument();
  });

  it("marks a required missing field flagged by the backend as Missing (attention)", () => {
    // NOT_READY_ANALYZE_RESPONSE flags objective/inputs/etc. via issues.
    render(
      <StructuredFields
        handoff={NOT_READY_HANDOFF}
        validation={NOT_READY_ANALYZE_RESPONSE.validation}
      />,
    );
    const objective = screen.getByText("Objective").closest(".field")!;
    expect(
      within(objective as HTMLElement).getByText(/missing/i),
    ).toBeInTheDocument();
    // Attention state: not marked optional-missing.
    expect(objective.getAttribute("data-optional-missing")).toBeNull();
    // The neutral optional note must NOT appear for a flagged field.
    expect(
      within(objective as HTMLElement).queryByText(/won't block the handoff/i),
    ).not.toBeInTheDocument();
  });

  it("presents an optional missing field neutrally on a READY handoff (no error styling)", () => {
    // context & constraints are MISSING but the backend raised no issues.
    render(
      <StructuredFields
        handoff={READY_WITH_OPTIONAL_MISSING_HANDOFF}
        validation={NO_ISSUES}
      />,
    );
    for (const label of ["Context", "Constraints", "Deadline"]) {
      const cell = screen.getByText(label).closest(".field")!;
      expect(
        within(cell as HTMLElement).getByText(/not provided/i),
      ).toBeInTheDocument();
      expect(
        within(cell as HTMLElement).getByText(
          /optional — this won't block the handoff/i,
        ),
      ).toBeInTheDocument();
      // Flagged neutrally, not as an error.
      expect(cell.getAttribute("data-optional-missing")).toBe("true");
    }
  });

  it("marks an ambiguous field but still shows its value", () => {
    render(
      <StructuredFields
        handoff={NOT_READY_HANDOFF}
        validation={NOT_READY_ANALYZE_RESPONSE.validation}
      />,
    );
    const deadline = screen.getByText("Deadline").closest(".field")!;
    expect(
      within(deadline as HTMLElement).getByText(/unclear/i),
    ).toBeInTheDocument();
    expect(within(deadline as HTMLElement).getByText("soon")).toBeInTheDocument();
  });

  it("marks a not-applicable field neutrally", () => {
    render(
      <StructuredFields
        handoff={NOT_READY_HANDOFF}
        validation={NOT_READY_ANALYZE_RESPONSE.validation}
      />,
    );
    const constraints = screen.getByText("Constraints").closest(".field")!;
    expect(
      within(constraints as HTMLElement).getByText(/not applicable/i),
    ).toBeInTheDocument();
  });
});
