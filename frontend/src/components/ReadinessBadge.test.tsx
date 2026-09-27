import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ReadinessBadge from "./ReadinessBadge";

describe("ReadinessBadge", () => {
  it("renders the backend ready state", () => {
    render(<ReadinessBadge state="ready" />);
    expect(screen.getByText("Ready to hand off")).toBeInTheDocument();
  });

  it("renders the needs-clarification state", () => {
    render(<ReadinessBadge state="needs_clarification" />);
    expect(screen.getByText("Almost there")).toBeInTheDocument();
  });

  it("renders the not-ready state", () => {
    render(<ReadinessBadge state="not_ready" />);
    expect(screen.getByText("More information needed")).toBeInTheDocument();
  });

  it("reflects only the prop — different props render different labels (no computation)", () => {
    const { rerender } = render(<ReadinessBadge state="ready" />);
    expect(screen.getByText("Ready to hand off")).toBeInTheDocument();
    rerender(<ReadinessBadge state="not_ready" />);
    expect(screen.getByText("More information needed")).toBeInTheDocument();
    expect(screen.queryByText("Ready to hand off")).not.toBeInTheDocument();
  });
});
