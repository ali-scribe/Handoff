import { useId, useState } from "react";

import { analyzeHandoff } from "../api/client";
import { toUserMessage } from "../api/errors";
import { useAsync } from "../hooks/useAsync";
import type { AnalyzeResponse } from "../types/handoff";
import DemoExamples from "./DemoExamples";
import ErrorBanner from "./ErrorBanner";
import Spinner from "./Spinner";

interface InputViewProps {
  onAnalyzed: (response: AnalyzeResponse) => void;
}

/**
 * The starting screen: state the product's purpose, collect the raw request,
 * and Analyze. Empty/whitespace input is blocked client-side purely for UX;
 * the backend remains authoritative.
 */
function InputView({ onAnalyzed }: InputViewProps) {
  const [text, setText] = useState("");
  const { isLoading, status, error, run } = useAsync();
  const textareaId = useId();

  const isBlank = text.trim().length === 0;

  async function handleAnalyze() {
    if (isBlank) return; // UX guard only; backend still validates.
    const response = await run(() => analyzeHandoff(text));
    if (response) {
      onAnalyzed(response);
    }
  }

  return (
    <>
    <section className="card" aria-labelledby="input-title">
      <h2 id="input-title" className="input-display">
        What needs to be handed off?
      </h2>
      <p className="muted">
        Paste a work request. Handoff checks whether someone else could actually
        execute it, and helps you close the gaps.
      </p>

      <label htmlFor={textareaId}>Work request</label>
      <textarea
        id={textareaId}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Paste or write the request here…"
      />

      {status === "error" && (
        <ErrorBanner message={toUserMessage(error)} onRetry={handleAnalyze} />
      )}

      <div className="button-row">
        <button
          type="button"
          className="primary"
          onClick={handleAnalyze}
          disabled={isBlank || isLoading}
        >
          Analyze
        </button>
        {isLoading && <Spinner label="Analyzing…" />}
      </div>

      {/*
        Demo examples load a pre-baked request into the textarea (below).
        They never submit — the user still clicks Analyze — and the text stays
        editable. Disabled only while an analysis is in flight.
      */}
      <DemoExamples onSelect={setText} disabled={isLoading} />
    </section>
    </>
  );
}

export default InputView;
