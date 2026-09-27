/**
 * Typed API errors and safe user-facing messages.
 *
 * The backend returns a stable error envelope {error: {code, message}}. The
 * client wraps every failure in an ApiError carrying that code, and the UI uses
 * toUserMessage() to render a safe, friendly string. No stack traces, provider
 * internals, or secrets are ever surfaced.
 */

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** Friendly copy per known backend/client error code. */
const FRIENDLY_MESSAGES: Record<string, string> = {
  // Clarification / answer application (HTTP 422)
  empty_answer: "Please provide an answer before applying.",
  invalid_target_field: "That answer can't be applied to that field.",
  contradiction_not_found: "That contradiction has already been resolved.",
  clarification_error: "That request couldn't be processed. Please try again.",
  // Request validation
  invalid_request: "The request was invalid. Please check your input.",
  // Extraction / provider (HTTP 5xx)
  empty_input: "Please enter a request to analyze.",
  provider_timeout: "The request took too long. Please try again.",
  server_configuration_error:
    "The server is not configured correctly. Please try again later.",
  provider_failure: "The analysis service had a problem. Please try again.",
  malformed_ai_response: "The analysis service had a problem. Please try again.",
  unexpected_ai_response: "The analysis service had a problem. Please try again.",
  schema_validation_failed:
    "The analysis service had a problem. Please try again.",
  extraction_error: "The analysis service had a problem. Please try again.",
  // Client-side transport codes
  timeout: "The request took too long. Please try again.",
  network: "Couldn't reach the server. Check your connection and try again.",
  http_error: "Something went wrong. Please try again.",
};

/**
 * Map any thrown value to a safe, user-facing message. Known error codes get
 * tailored copy; otherwise a generic fallback is used.
 */
export function toUserMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return FRIENDLY_MESSAGES[err.code] ?? "Something went wrong. Please try again.";
  }
  return "Something went wrong. Please try again.";
}
