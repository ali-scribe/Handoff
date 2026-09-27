import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ClarificationView from "./ClarificationView";
import { applyAnswers } from "../api/client";
import { ApiError } from "../api/errors";
import {
  APPLIED_READY_RESPONSE,
  CONTRADICTION_HANDOFF,
  CONTRADICTION_QUESTION,
  NOT_READY_HANDOFF,
  SAMPLE_QUESTIONS,
} from "../test/fixtures";

vi.mock("../api/client", () => ({
  applyAnswers: vi.fn(),
}));

const applyMock = vi.mocked(applyAnswers);

beforeEach(() => {
  applyMock.mockReset();
  applyMock.mockResolvedValue(APPLIED_READY_RESPONSE);
});

describe("ClarificationView", () => {
  it("renders exactly the backend questions (count and text)", () => {
    render(
      <ClarificationView
        handoff={NOT_READY_HANDOFF}
        questions={SAMPLE_QUESTIONS}
        onApplied={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    for (const q of SAMPLE_QUESTIONS) {
      expect(screen.getByText(q.text)).toBeInTheDocument();
    }
    // One text input per question (SAMPLE_QUESTIONS has 2).
    expect(screen.getAllByRole("textbox")).toHaveLength(SAMPLE_QUESTIONS.length);
  });

  it("collects non-empty answers and sends them to applyAnswers", async () => {
    const onApplied = vi.fn();
    render(
      <ClarificationView
        handoff={NOT_READY_HANDOFF}
        questions={SAMPLE_QUESTIONS}
        onApplied={onApplied}
        onCancel={vi.fn()}
      />,
    );
    const inputs = screen.getAllByRole("textbox");
    // Answer the first (objective), leave the second (deadline) blank.
    fireEvent.change(inputs[0], { target: { value: "Fix the login bug" } });
    fireEvent.click(screen.getByRole("button", { name: /apply answers/i }));

    await waitFor(() => expect(applyMock).toHaveBeenCalledOnce());
    const [handoffArg, answersArg, resolveArg] = applyMock.mock.calls[0];
    expect(handoffArg).toBe(NOT_READY_HANDOFF);
    // Empty-answer field is omitted.
    expect(answersArg).toEqual([{ field: "objective", value: "Fix the login bug" }]);
    expect(resolveArg).toEqual([]);
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(APPLIED_READY_RESPONSE));
  });

  it("omits fields with only whitespace answers", async () => {
    render(
      <ClarificationView
        handoff={NOT_READY_HANDOFF}
        questions={SAMPLE_QUESTIONS}
        onApplied={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.change(screen.getAllByRole("textbox")[0], { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: /apply answers/i }));

    await waitFor(() => expect(applyMock).toHaveBeenCalledOnce());
    expect(applyMock.mock.calls[0][1]).toEqual([]);
  });

  it("shows a resolve control for a contradiction question and sends the pair only when chosen", async () => {
    render(
      <ClarificationView
        handoff={CONTRADICTION_HANDOFF}
        questions={[CONTRADICTION_QUESTION]}
        onApplied={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const resolveCheckbox = screen.getByRole("checkbox");
    expect(resolveCheckbox).toBeInTheDocument();

    fireEvent.click(resolveCheckbox);
    fireEvent.click(screen.getByRole("button", { name: /apply answers/i }));

    await waitFor(() => expect(applyMock).toHaveBeenCalledOnce());
    expect(applyMock.mock.calls[0][2]).toEqual([["deadline", "dependencies"]]);
  });

  it("does not resolve a contradiction unless the control is chosen", async () => {
    render(
      <ClarificationView
        handoff={CONTRADICTION_HANDOFF}
        questions={[CONTRADICTION_QUESTION]}
        onApplied={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /apply answers/i }));

    await waitFor(() => expect(applyMock).toHaveBeenCalledOnce());
    expect(applyMock.mock.calls[0][2]).toEqual([]);
  });

  it("shows a safe error when apply-answers fails", async () => {
    applyMock.mockRejectedValue(new ApiError("empty_answer", "no", 422));
    render(
      <ClarificationView
        handoff={NOT_READY_HANDOFF}
        questions={SAMPLE_QUESTIONS}
        onApplied={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.change(screen.getAllByRole("textbox")[0], { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /apply answers/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/provide an answer/i);
  });
});
