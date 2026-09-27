import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DemoExamples from "./DemoExamples";
import { DEMO_EXAMPLES } from "../data/demoExamples";

describe("DemoExamples", () => {
  it("renders exactly three example options", () => {
    render(<DemoExamples onSelect={vi.fn()} />);
    // One button per example (the section heading is not a button).
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(DEMO_EXAMPLES.length);
    expect(DEMO_EXAMPLES).toHaveLength(3);
  });

  it("gives each example a useful accessible name", () => {
    render(<DemoExamples onSelect={vi.fn()} />);
    for (const example of DEMO_EXAMPLES) {
      // Accessible name includes the title (and description) so it is meaningful.
      const btn = screen.getByRole("button", {
        name: new RegExp(example.title, "i"),
      });
      expect(btn).toBeInTheDocument();
    }
  });

  it("calls onSelect with the example's text when clicked", () => {
    const onSelect = vi.fn();
    render(<DemoExamples onSelect={onSelect} />);
    fireEvent.click(
      screen.getByRole("button", { name: /ready request/i }),
    );
    const readyExample = DEMO_EXAMPLES.find((e) => e.id === "ready")!;
    expect(onSelect).toHaveBeenCalledWith(readyExample.text);
  });

  it("disables the options when disabled is true", () => {
    render(<DemoExamples onSelect={vi.fn()} disabled />);
    for (const btn of screen.getAllByRole("button")) {
      expect(btn).toBeDisabled();
    }
  });
});
