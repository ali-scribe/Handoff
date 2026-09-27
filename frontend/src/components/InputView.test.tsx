import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InputView from "./InputView";
import { analyzeHandoff } from "../api/client";
import { ApiError } from "../api/errors";
import { READY_ANALYZE_RESPONSE } from "../test/fixtures";

vi.mock("../api/client", () => ({
  analyzeHandoff: vi.fn(),
}));

const analyzeMock = vi.mocked(analyzeHandoff);

beforeEach(() => {
  analyzeMock.mockReset();
});

describe("InputView", () => {
  it("renders the textarea, example guidance, and Analyze button", () => {
    render(<InputView onAnalyzed={vi.fn()} />);
    expect(screen.getByLabelText(/work request/i)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /try an example/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze/i })).toBeInTheDocument();
  });

  it("populates the textarea from a demo example without submitting", () => {
    const onAnalyzed = vi.fn();
    render(<InputView onAnalyzed={onAnalyzed} />);
    const textarea = screen.getByLabelText(/work request/i) as HTMLTextAreaElement;
    expect(textarea.value).toBe("");

    fireEvent.click(
      screen.getByRole("button", { name: /load example: incomplete request/i }),
    );

    // Textarea is populated, stays on the input screen, and does NOT analyze.
    expect(textarea.value.length).toBeGreaterThan(0);
    expect(analyzeMock).not.toHaveBeenCalled();
    expect(onAnalyzed).not.toHaveBeenCalled();

    // Still editable: the user can modify the loaded text.
    fireEvent.change(textarea, { target: { value: textarea.value + " extra" } });
    expect(textarea.value).toMatch(/extra$/);
  });

  it("disables Analyze for empty/whitespace input", () => {
    render(<InputView onAnalyzed={vi.fn()} />);
    const button = screen.getByRole("button", { name: /analyze/i });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/work request/i), {
      target: { value: "   " },
    });
    expect(button).toBeDisabled();
    expect(analyzeMock).not.toHaveBeenCalled();
  });

  it("calls analyzeHandoff with the entered text and forwards the response", async () => {
    analyzeMock.mockResolvedValue(READY_ANALYZE_RESPONSE);
    const onAnalyzed = vi.fn();
    render(<InputView onAnalyzed={onAnalyzed} />);

    fireEvent.change(screen.getByLabelText(/work request/i), {
      target: { value: "fix the login bug" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    await waitFor(() =>
      expect(analyzeMock).toHaveBeenCalledWith("fix the login bug"),
    );
    expect(onAnalyzed).toHaveBeenCalledWith(READY_ANALYZE_RESPONSE);
  });

  it("shows a loading indicator while analyzing", async () => {
    let resolve: (value: typeof READY_ANALYZE_RESPONSE) => void = () => {};
    analyzeMock.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    render(<InputView onAnalyzed={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/work request/i), {
      target: { value: "text" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(await screen.findByText(/analyzing/i)).toBeInTheDocument();
    resolve(READY_ANALYZE_RESPONSE);
  });

  it("shows a safe error with retry when analysis fails", async () => {
    analyzeMock.mockRejectedValue(new ApiError("provider_failure", "boom", 502));
    render(<InputView onAnalyzed={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/work request/i), {
      target: { value: "text" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/analysis service had a problem/i);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
