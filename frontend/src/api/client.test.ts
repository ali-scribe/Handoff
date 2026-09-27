import { afterEach, describe, expect, it, vi } from "vitest";

import {
  analyzeHandoff,
  applyAnswers,
  formatHandoff,
  getClarificationQuestions,
} from "./client";
import { ApiError } from "./errors";
import type { StructuredHandoff } from "../types/handoff";

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
  } as unknown as Response;
}

const HANDOFF: StructuredHandoff = {
  objective: { value: "Do the thing", condition: "present" },
  owner: { value: null, condition: "missing" },
  inputs: { value: null, condition: "missing" },
  expected_output: { value: null, condition: "missing" },
  deadline: { value: null, condition: "missing" },
  acceptance_criteria: { value: null, condition: "missing" },
  context: { value: null, condition: "missing" },
  constraints: { value: null, condition: "not_applicable" },
  dependencies: { value: null, condition: "not_applicable" },
  contradictions: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("analyzeHandoff", () => {
  it("POSTs text to the analyze endpoint and returns parsed data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ handoff: HANDOFF, validation: { readiness_state: "not_ready", issues: [] } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await analyzeHandoff("fix the bug");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/handoff/analyze");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ text: "fix the bug" });
    expect(result.validation.readiness_state).toBe("not_ready");
  });
});

describe("getClarificationQuestions", () => {
  it("POSTs the handoff and unwraps .questions", async () => {
    const questions = [
      { field: "owner", secondary_field: null, issue_types: ["ambiguous_ownership"], text: "Who owns this?" },
    ];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ questions }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getClarificationQuestions(HANDOFF);

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/handoff/clarify");
    expect(JSON.parse(init.body)).toEqual({ handoff: HANDOFF });
    expect(result).toEqual(questions);
  });
});

describe("applyAnswers", () => {
  it("POSTs handoff, answers, and resolve_contradictions in the DTO shape", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ handoff: HANDOFF, validation: { readiness_state: "ready", issues: [] } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const answers = [{ field: "owner" as const, value: "Alice" }];
    await applyAnswers(HANDOFF, answers, [["deadline", "dependencies"]]);

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/handoff/apply-answers");
    expect(JSON.parse(init.body)).toEqual({
      handoff: HANDOFF,
      answers,
      resolve_contradictions: [["deadline", "dependencies"]],
    });
  });

  it("sends an empty resolve_contradictions list when none are given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ handoff: HANDOFF, validation: { readiness_state: "ready", issues: [] } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await applyAnswers(HANDOFF, [], []);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.resolve_contradictions).toEqual([]);
  });
});

describe("formatHandoff", () => {
  it("POSTs the handoff and unwraps .text", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ text: "FORMATTED" }));
    vi.stubGlobal("fetch", fetchMock);

    const text = await formatHandoff(HANDOFF);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/handoff/format");
    expect(text).toBe("FORMATTED");
  });
});

describe("error handling", () => {
  it("maps a backend error envelope to a typed ApiError with its code", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ error: { code: "empty_answer", message: "no" } }, false, 422),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(applyAnswers(HANDOFF, [], [])).rejects.toMatchObject({
      code: "empty_answer",
      status: 422,
    });
  });

  it("maps a non-envelope failure to a generic http_error ApiError", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    const error = await analyzeHandoff("x").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("http_error");
    expect(error.status).toBe(500);
  });

  it("maps an aborted request to a timeout ApiError", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new DOMException("aborted", "AbortError"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(analyzeHandoff("x")).rejects.toMatchObject({ code: "timeout" });
  });

  it("maps a network failure to a network ApiError", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(analyzeHandoff("x")).rejects.toMatchObject({ code: "network" });
  });
});
