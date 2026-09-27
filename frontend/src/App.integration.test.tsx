import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  analyzeHandoff,
  applyAnswers,
  formatHandoff,
  getClarificationQuestions,
} from "./api/client";
import {
  APPLIED_READY_RESPONSE,
  NOT_READY_ANALYZE_RESPONSE,
  SAMPLE_QUESTIONS,
} from "./test/fixtures";

vi.mock("./api/client", () => ({
  analyzeHandoff: vi.fn(),
  getClarificationQuestions: vi.fn(),
  applyAnswers: vi.fn(),
  formatHandoff: vi.fn(),
  getHealth: vi.fn(),
}));

const analyzeMock = vi.mocked(analyzeHandoff);
const clarifyMock = vi.mocked(getClarificationQuestions);
const applyMock = vi.mocked(applyAnswers);
const formatMock = vi.mocked(formatHandoff);

beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function analyzeToResults() {
  analyzeMock.mockResolvedValue(NOT_READY_ANALYZE_RESPONSE);
  render(<App />);
  fireEvent.change(screen.getByLabelText(/work request/i), {
    target: { value: "fix the login bug" },
  });
  fireEvent.click(screen.getByRole("button", { name: /analyze/i }));
  // Results view shows the backend readiness.
  expect(await screen.findByText("More information needed")).toBeInTheDocument();
}

describe("App integration", () => {
  it("analyzes and shows the results view with readiness, fields, and issues", async () => {
    await analyzeToResults();
    expect(screen.getByRole("heading", { name: "Analysis" })).toBeInTheDocument();
    expect(screen.getByText("Expected output")).toBeInTheDocument();
    expect(screen.getByText("The objective is missing.")).toBeInTheDocument();
  });

  it("fetches clarification questions, applies answers, and RETURNS TO RESULTS even when READY", async () => {
    await analyzeToResults();

    clarifyMock.mockResolvedValue(SAMPLE_QUESTIONS);
    fireEvent.click(
      screen.getByRole("button", { name: /answer clarification questions/i }),
    );
    // Exact backend questions rendered.
    expect(await screen.findByText(SAMPLE_QUESTIONS[0].text)).toBeInTheDocument();

    // Apply answers; backend now reports READY.
    applyMock.mockResolvedValue(APPLIED_READY_RESPONSE);
    fireEvent.change(screen.getAllByRole("textbox")[0], {
      target: { value: "Fix the login bug properly" },
    });
    fireEvent.click(screen.getByRole("button", { name: /apply answers/i }));

    // Critical rule: even though readiness is READY, we stay on Results and do
    // NOT auto-jump to the execution-ready view.
    expect(await screen.findByText("Ready to hand off")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Analysis" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: /your handoff is ready/i }),
    ).not.toBeInTheDocument();
    // Format is only reachable by explicit user action.
    expect(
      screen.getByRole("button", { name: /format handoff/i }),
    ).toBeInTheDocument();
  });

  it("shows the execution-ready view only after the explicit Format action", async () => {
    await analyzeToResults();

    formatMock.mockResolvedValue("Objective: Fix the login bug\nOwner: Alice");
    fireEvent.click(screen.getByRole("button", { name: /format handoff/i }));

    expect(
      await screen.findByRole("heading", { name: /your handoff is ready/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Objective: Fix the login bug/)).toBeInTheDocument();
    await waitFor(() => expect(formatMock).toHaveBeenCalledOnce());
  });

  it("resets back to the input view via Start another handoff", async () => {
    await analyzeToResults();
    formatMock.mockResolvedValue("Some formatted handoff");
    fireEvent.click(screen.getByRole("button", { name: /format handoff/i }));
    await screen.findByRole("heading", { name: /your handoff is ready/i });

    fireEvent.click(screen.getByRole("button", { name: /start another handoff/i }));
    expect(screen.getByLabelText(/work request/i)).toBeInTheDocument();
  });

  it("drives the decorative ProcessFlow stage from the app journey", async () => {
    analyzeMock.mockResolvedValue(NOT_READY_ANALYZE_RESPONSE);
    const { container } = render(<App />);
    const stage = () =>
      container.querySelector(".process-flow")?.getAttribute("data-stage");

    // Input screen.
    expect(stage()).toBe("input");

    // Analyze -> results.
    fireEvent.change(screen.getByLabelText(/work request/i), {
      target: { value: "fix the login bug" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));
    expect(await screen.findByText("More information needed")).toBeInTheDocument();
    expect(stage()).toBe("results");

    // Open clarification questions -> clarifying.
    clarifyMock.mockResolvedValue(SAMPLE_QUESTIONS);
    fireEvent.click(
      screen.getByRole("button", { name: /answer clarification questions/i }),
    );
    expect(await screen.findByText(SAMPLE_QUESTIONS[0].text)).toBeInTheDocument();
    await waitFor(() => expect(stage()).toBe("clarifying"));

    // Apply answers -> back to results (clarifying clears).
    applyMock.mockResolvedValue(APPLIED_READY_RESPONSE);
    fireEvent.click(screen.getByRole("button", { name: /apply answers/i }));
    expect(await screen.findByText("Ready to hand off")).toBeInTheDocument();
    await waitFor(() => expect(stage()).toBe("results"));

    // Explicit format -> ready.
    formatMock.mockResolvedValue("Objective: Fix the login bug");
    fireEvent.click(screen.getByRole("button", { name: /format handoff/i }));
    await screen.findByRole("heading", { name: /your handoff is ready/i });
    expect(stage()).toBe("ready");
  });
});

