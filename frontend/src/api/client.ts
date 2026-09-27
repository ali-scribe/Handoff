import type { HealthResponse } from "../types/health";
import type {
  AnalyzeResponse,
  Answer,
  ApplyAnswersResponse,
  ContradictionPair,
  Question,
  StructuredHandoff,
} from "../types/handoff";
import { ApiError } from "./errors";

/**
 * The single network layer for the frontend. Every backend call goes through
 * here — components never call fetch() directly. Requests go to /api/* and are
 * proxied to FastAPI during development.
 */

/** Client-side request timeout. Backend also enforces its own timeouts. */
const REQUEST_TIMEOUT_MS = 30_000;

/** Shape of the backend error envelope: {error: {code, message}}. */
interface ErrorEnvelope {
  error?: { code?: unknown; message?: unknown };
}

/**
 * POST a JSON body and parse a JSON response. Translates HTTP errors, the
 * backend error envelope, network failures, and timeouts into a typed ApiError.
 */
async function postJson<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    // AbortError (timeout) vs any other network failure.
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("timeout", "The request timed out.", 0);
    }
    throw new ApiError("network", "Network request failed.", 0);
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as TRes;
}

/** Build an ApiError from a non-2xx response, honoring the backend envelope. */
async function toApiError(response: Response): Promise<ApiError> {
  try {
    const data = (await response.json()) as ErrorEnvelope;
    const code = data.error?.code;
    const message = data.error?.message;
    if (typeof code === "string") {
      const safeMessage =
        typeof message === "string" ? message : "Request failed.";
      return new ApiError(code, safeMessage, response.status);
    }
  } catch {
    // Body was not the expected JSON envelope; fall through to a generic error.
  }
  return new ApiError(
    "http_error",
    `Request failed (${response.status}).`,
    response.status,
  );
}

/** GET /api/health — kept for connectivity checks; not surfaced in the UI. */
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new ApiError("http_error", `Health request failed.`, response.status);
  }
  return (await response.json()) as HealthResponse;
}

/** POST /api/handoff/analyze — extract + validate raw request text. */
export async function analyzeHandoff(text: string): Promise<AnalyzeResponse> {
  return postJson<{ text: string }, AnalyzeResponse>("/api/handoff/analyze", {
    text,
  });
}

/** POST /api/handoff/clarify — deterministic questions for the current handoff. */
export async function getClarificationQuestions(
  handoff: StructuredHandoff,
): Promise<Question[]> {
  const data = await postJson<
    { handoff: StructuredHandoff },
    { questions: Question[] }
  >("/api/handoff/clarify", { handoff });
  return data.questions;
}

/** POST /api/handoff/apply-answers — apply answers + explicit contradiction resolutions, then re-validate. */
export async function applyAnswers(
  handoff: StructuredHandoff,
  answers: Answer[],
  resolveContradictions: ContradictionPair[],
): Promise<ApplyAnswersResponse> {
  return postJson<
    {
      handoff: StructuredHandoff;
      answers: Answer[];
      resolve_contradictions: ContradictionPair[];
    },
    ApplyAnswersResponse
  >("/api/handoff/apply-answers", {
    handoff,
    answers,
    resolve_contradictions: resolveContradictions,
  });
}

/** POST /api/handoff/format — render the current handoff to copyable text. */
export async function formatHandoff(
  handoff: StructuredHandoff,
): Promise<string> {
  const data = await postJson<{ handoff: StructuredHandoff }, { text: string }>(
    "/api/handoff/format",
    { handoff },
  );
  return data.text;
}
