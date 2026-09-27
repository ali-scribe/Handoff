import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import App from "./App";

// Mock the API client so no network is touched. The initial render only shows
// the input phase, which does not call the client until the user analyzes.
vi.mock("./api/client", () => ({
  analyzeHandoff: vi.fn(),
  getClarificationQuestions: vi.fn(),
  applyAnswers: vi.fn(),
  formatHandoff: vi.fn(),
  getHealth: vi.fn(),
}));

describe("App shell", () => {
  it("renders the header and starts on the input phase", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Handoff" })).toBeInTheDocument();
    // Input phase shows the textarea and the Analyze action.
    expect(
      screen.getByRole("button", { name: /analyze/i }),
    ).toBeInTheDocument();
  });

  it("does not render a health/connectivity indicator", () => {
    render(<App />);
    expect(screen.queryByText(/backend:/i)).not.toBeInTheDocument();
  });
});
