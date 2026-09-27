import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ProcessFlow, { type ProcessStage } from "./ProcessFlow";

/** Read the node states in order from a rendered ProcessFlow. */
function nodeStates(container: HTMLElement): (string | null)[] {
  return Array.from(container.querySelectorAll(".process-node")).map((n) =>
    n.getAttribute("data-node-state"),
  );
}

describe("ProcessFlow", () => {
  it("is decorative (aria-hidden) and reflects the stage on the root", () => {
    const { container } = render(<ProcessFlow stage="input" />);
    const root = container.querySelector(".process-flow")!;
    expect(root).toHaveAttribute("aria-hidden", "true");
    expect(root).toHaveAttribute("data-stage", "input");
  });

  it("marks only the Input node active on the input stage", () => {
    const { container } = render(<ProcessFlow stage="input" />);
    expect(nodeStates(container)).toEqual([
      "active",
      "muted",
      "muted",
      "muted",
    ]);
  });

  it("advances to Results, with Input completed", () => {
    const { container } = render(<ProcessFlow stage="results" />);
    expect(nodeStates(container)).toEqual([
      "complete",
      "active",
      "muted",
      "muted",
    ]);
  });

  it("marks Clarify active with earlier stages completed", () => {
    const { container } = render(<ProcessFlow stage="clarifying" />);
    expect(nodeStates(container)).toEqual([
      "complete",
      "complete",
      "active",
      "muted",
    ]);
  });

  it("marks the final Ready node active with the whole path completed", () => {
    const { container } = render(<ProcessFlow stage="ready" />);
    expect(nodeStates(container)).toEqual([
      "complete",
      "complete",
      "complete",
      "active",
    ]);
    const finalNode = container.querySelector('[data-final="true"]')!;
    expect(finalNode).toHaveAttribute("data-node-state", "active");
  });

  it("activates connecting lines up to the current stage", () => {
    const stages: ProcessStage[] = ["input", "results", "clarifying", "ready"];
    const completedCounts = stages.map((stage) => {
      const { container } = render(<ProcessFlow stage={stage} />);
      return container.querySelectorAll('.process-line[data-complete="true"]')
        .length;
    });
    // input:0 completed lines, results:1, clarifying:2, ready:3
    expect(completedCounts).toEqual([0, 1, 2, 3]);
  });
});
