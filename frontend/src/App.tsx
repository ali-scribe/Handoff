import { useState } from "react";

import Header from "./components/Header";
import InputView from "./components/InputView";
import ResultsView from "./components/ResultsView";
import ExecutionReadyView from "./components/ExecutionReadyView";
import ProcessFlow, { type ProcessStage } from "./components/ProcessFlow";
import type {
  AnalyzeResponse,
  ApplyAnswersResponse,
  StructuredHandoff,
  ValidationResult,
} from "./types/handoff";

/**
 * Top-level shell and phase state machine.
 *
 * Flow: input -> results -> (clarify/apply, staying in results) -> ready.
 * The backend is the source of truth: this component stores the handoff and
 * validation exactly as returned and never computes readiness. State is plain
 * React hooks — no router, no state library.
 */
type Phase = "input" | "results" | "ready";

function App() {
  const [phase, setPhase] = useState<Phase>("input");
  const [handoff, setHandoff] = useState<StructuredHandoff | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [formattedText, setFormattedText] = useState<string | null>(null);
  // Presentational-only signal: whether the results screen is currently showing
  // clarification questions. Reported by ResultsView; it does NOT drive the
  // phase machine or any readiness logic — it only feeds the decorative
  // ProcessFlow indicator below.
  const [isClarifying, setIsClarifying] = useState(false);

  /** Analyze succeeded: store server truth and move to results. */
  function handleAnalyzed(response: AnalyzeResponse) {
    setHandoff(response.handoff);
    setValidation(response.validation);
    setPhase("results");
  }

  /**
   * apply-answers succeeded: adopt the updated handoff + validation and ALWAYS
   * return to results, even when readiness is "ready". The user must explicitly
   * choose "Format handoff" from results (approved decision).
   */
  function handleApplied(response: ApplyAnswersResponse) {
    setHandoff(response.handoff);
    setValidation(response.validation);
    setPhase("results");
  }

  /** User explicitly chose to format: store the text and show the ready view. */
  function handleFormatted(text: string) {
    setFormattedText(text);
    setPhase("ready");
  }

  /** Start another handoff: clear all state back to the input phase. */
  function handleReset() {
    setHandoff(null);
    setValidation(null);
    setFormattedText(null);
    setIsClarifying(false);
    setPhase("input");
  }

  /**
   * Map the existing app state to a decorative process stage for ProcessFlow.
   * This is a pure view derivation — no new source of truth for readiness.
   */
  const processStage: ProcessStage =
    phase === "input"
      ? "input"
      : phase === "ready"
        ? "ready"
        : isClarifying
          ? "clarifying"
          : "results";

  return (
    <div className="app">
      <Header />
      {phase === "input" && <InputView onAnalyzed={handleAnalyzed} />}
      {phase === "results" && handoff && validation && (
        <ResultsView
          handoff={handoff}
          validation={validation}
          onApplied={handleApplied}
          onFormatted={handleFormatted}
          onClarifyingChange={setIsClarifying}
        />
      )}
      {phase === "ready" && handoff && validation && formattedText !== null && (
        <ExecutionReadyView
          formattedText={formattedText}
          readinessState={validation.readiness_state}
          onReset={handleReset}
        />
      )}

      <ProcessFlow stage={processStage} />
    </div>
  );
}

export default App;
