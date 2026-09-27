import { useState } from "react";

import type { ReadinessState } from "../types/handoff";
import ReadinessBadge from "./ReadinessBadge";

interface ExecutionReadyViewProps {
  formattedText: string;
  readinessState: ReadinessState;
  onReset: () => void;
}

/**
 * Displays the backend-formatted handoff text (already fetched) in a copyable
 * block, with a Copy button and copy-success feedback, the backend-provided
 * readiness, and a reset to start another handoff. This view performs no
 * network calls and never regenerates or alters the formatted text.
 */
function ExecutionReadyView({
  formattedText,
  readinessState,
  onReset,
}: ExecutionReadyViewProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(formattedText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard may be unavailable; keep the text visible for manual copy.
      setCopied(false);
    }
  }

  return (
    <section className="card" aria-labelledby="ready-title">
      <div className="button-row" style={{ marginTop: 0 }}>
        <h2 id="ready-title" className="section-title" style={{ margin: 0 }}>
          Your handoff is ready
        </h2>
        <ReadinessBadge state={readinessState} />
      </div>
      <p className="backend-note">
        Readiness above is determined by the backend, not this page.
      </p>

      <pre className="formatted-output">{formattedText}</pre>

      <div className="button-row">
        <button type="button" className="primary" onClick={handleCopy}>
          Copy handoff
        </button>
        {copied && (
          <span className="copy-success" role="status" aria-live="polite">
            ✓ Copied
          </span>
        )}
        <button type="button" onClick={onReset}>
          Start another handoff
        </button>
      </div>
    </section>
  );
}

export default ExecutionReadyView;
