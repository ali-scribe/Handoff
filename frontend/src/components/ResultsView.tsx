import { useEffect, useState } from "react";

import { formatHandoff, getClarificationQuestions } from "../api/client";
import { toUserMessage } from "../api/errors";
import { useAsync } from "../hooks/useAsync";
import type {
  ApplyAnswersResponse,
  Question,
  ReadinessState,
  StructuredHandoff,
  ValidationResult,
} from "../types/handoff";
import ClarificationView from "./ClarificationView";
import ErrorBanner from "./ErrorBanner";
import IssueList from "./IssueList";
import ReadinessBadge from "./ReadinessBadge";
import Spinner from "./Spinner";
import StructuredFields from "./StructuredFields";

interface ResultsViewProps {
  handoff: StructuredHandoff;
  validation: ValidationResult;
  onApplied: (response: ApplyAnswersResponse) => void;
  onFormatted: (text: string) => void;
  /**
   * Optional presentational callback: reports whether clarification questions
   * are currently shown, so the decorative ProcessFlow can reflect the
   * "clarifying" stage. Does not affect any logic here.
   */
  onClarifyingChange?: (clarifying: boolean) => void;
}

/** Calm supporting line for each readiness state (display only). */
const READINESS_SUBTEXT: Record<ReadinessState, string> = {
  ready: "This handoff has what someone needs to execute it.",
  needs_clarification: "A few details would make this clearer.",
  not_ready: "Key details are missing before this can be handed off.",
};

/**
 * The results screen: shows the backend readiness (as the visual hero), the
 * structured fields, and what's missing. From here the user can fetch
 * clarification questions (backend generated) or explicitly format the handoff.
 * No readiness/severity logic lives here — everything is rendered from the
 * backend response.
 */
function ResultsView({
  handoff,
  validation,
  onApplied,
  onFormatted,
  onClarifyingChange,
}: ResultsViewProps) {
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const clarifyAsync = useAsync();
  const formatAsync = useAsync();

  const hasIssues = validation.issues.length > 0;
  const state = validation.readiness_state;

  // Report clarifying state upward for the decorative ProcessFlow. Reset to
  // false when this view unmounts so the indicator never sticks on "clarifying".
  const clarifying = questions !== null;
  useEffect(() => {
    onClarifyingChange?.(clarifying);
    return () => onClarifyingChange?.(false);
  }, [clarifying, onClarifyingChange]);

  async function handleClarify() {
    const result = await clarifyAsync.run(() =>
      getClarificationQuestions(handoff),
    );
    if (result) {
      setQuestions(result);
    }
  }

  async function handleFormat() {
    const text = await formatAsync.run(() => formatHandoff(handoff));
    if (text !== undefined) {
      onFormatted(text);
    }
  }

  return (
    <section className="card" aria-labelledby="results-title">
      <h2 id="results-title" className="section-title">
        Analysis
      </h2>

      <div className="readiness-hero" data-state={state}>
        <ReadinessBadge state={state} />
        <p className="readiness-hero-sub">{READINESS_SUBTEXT[state]}</p>
      </div>

      <h3 className="section-title">Structured handoff</h3>
      <StructuredFields handoff={handoff} validation={validation} />

      <h3 className="issues-label">What's missing</h3>
      <IssueList issues={validation.issues} />

      {clarifyAsync.status === "error" && (
        <ErrorBanner
          message={toUserMessage(clarifyAsync.error)}
          onRetry={handleClarify}
        />
      )}
      {formatAsync.status === "error" && (
        <ErrorBanner
          message={toUserMessage(formatAsync.error)}
          onRetry={handleFormat}
        />
      )}

      {questions === null ? (
        <div className="button-row">
          {hasIssues && (
            <button
              type="button"
              className="primary"
              onClick={handleClarify}
              disabled={clarifyAsync.isLoading}
            >
              Answer clarification questions
            </button>
          )}
          <button
            type="button"
            onClick={handleFormat}
            disabled={formatAsync.isLoading}
          >
            Format handoff
          </button>
          {clarifyAsync.isLoading && <Spinner label="Loading questions…" />}
          {formatAsync.isLoading && <Spinner label="Formatting…" />}
        </div>
      ) : (
        <ClarificationView
          handoff={handoff}
          questions={questions}
          onApplied={(response) => {
            setQuestions(null);
            onApplied(response);
          }}
          onCancel={() => setQuestions(null)}
        />
      )}
    </section>
  );
}

export default ResultsView;

