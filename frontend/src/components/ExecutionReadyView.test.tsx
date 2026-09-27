import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ExecutionReadyView from "./ExecutionReadyView";

const FORMATTED = "Objective: Ship the report\nOwner: Alice";

let writeText: ReturnType<typeof vi.fn>;

beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ExecutionReadyView", () => {
  it("renders the backend-formatted text", () => {
    render(
      <ExecutionReadyView
        formattedText={FORMATTED}
        readinessState="ready"
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText(/Ship the report/)).toBeInTheDocument();
    expect(screen.getByText(/Owner: Alice/)).toBeInTheDocument();
  });

  it("shows the backend readiness and notes it is backend-provided", () => {
    render(
      <ExecutionReadyView
        formattedText={FORMATTED}
        readinessState="ready"
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText("Ready to hand off")).toBeInTheDocument();
    expect(screen.getByText(/determined by the backend/i)).toBeInTheDocument();
  });

  it("copies the text and shows success feedback", async () => {
    render(
      <ExecutionReadyView
        formattedText={FORMATTED}
        readinessState="ready"
        onReset={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /copy handoff/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(FORMATTED));
    expect(await screen.findByText(/copied/i)).toBeInTheDocument();
  });

  it("calls onReset when starting another handoff", () => {
    const onReset = vi.fn();
    render(
      <ExecutionReadyView
        formattedText={FORMATTED}
        readinessState="ready"
        onReset={onReset}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /start another handoff/i }));
    expect(onReset).toHaveBeenCalledOnce();
  });
});
