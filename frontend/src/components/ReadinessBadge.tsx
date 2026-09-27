import type { ReadinessState } from "../types/handoff";

/** Human-friendly, display-only labels for each backend readiness state. */
const READINESS_LABELS: Record<ReadinessState, string> = {
  ready: "Ready to hand off",
  needs_clarification: "Almost there",
  not_ready: "More information needed",
};

interface ReadinessBadgeProps {
  state: ReadinessState;
}

/**
 * Renders the backend-provided readiness state as a calm pill. Purely
 * presentational — the label is derived only from the prop; the frontend never
 * computes readiness.
 */
function ReadinessBadge({ state }: ReadinessBadgeProps) {
  return (
    <span className="readiness-badge" data-state={state}>
      {READINESS_LABELS[state]}
    </span>
  );
}

export default ReadinessBadge;
