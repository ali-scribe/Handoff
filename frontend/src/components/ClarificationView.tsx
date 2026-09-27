import { useState } from "react";

import { applyAnswers } from "../api/client";
import { toUserMessage } from "../api/errors";
import { useAsync } from "../hooks/useAsync";
import {
  FIELD_LABELS,
  type Answer,
  type ApplyAnswersResponse,
  type ContradictionPair,
  type HandoffFieldName,
  type Question,
  type StructuredHandoff,
} from "../types/handoff";
import ErrorBanner from "./ErrorBanner";
import Spinner from "./Spinner";

interface ClarificationViewProps {
  handoff: StructuredHandoff;
  questions: Question[];
  onApplied: (response: ApplyAnswersResponse) => void;
  onCancel: () => void;
}

/**
 * Renders exactly the backend-generated questions as a calm, guided completion
 * step. Each question has one answer input; contradiction questions add an
 * explicit "resolve" control (never auto-resolved). On Apply, non-empty answers
 * and any chosen contradiction resolutions are sent to the backend; the
 * frontend invents nothing.
 */
function ClarificationView({
  handoff,
  questions,
  onApplied,
  onCancel,
}: ClarificationViewProps) {
  // Answer text keyed by field name (one input per question).
  const [answers, setAnswers] = useState<Record<string, string>>({});
  // Contradiction pairs the user explicitly chose to resolve, keyed by question index.
  const [resolved, setResolved] = useState<Record<number, boolean>>({});
  const { isLoading, status, error, run } = useAsync();

  function setAnswer(field: HandoffFieldName, value: string) {
    setAnswers((prev) => ({ ...prev, [field]: value }));
  }

  function toggleResolve(index: number) {
    setResolved((prev) => ({ ...prev, [index]: !prev[index] }));
  }

  async function handleApply() {
    // Collect only non-empty answers (UX guard; backend stays authoritative).
    const collectedAnswers: Answer[] = [];
    for (const question of questions) {
      const value = answers[question.field]?.trim();
      if (value) {
        collectedAnswers.push({ field: question.field, value });
      }
    }

    // Collect only explicitly-authorized contradiction resolutions.
    const resolveContradictions: ContradictionPair[] = [];
    questions.forEach((question, index) => {
      if (question.secondary_field && resolved[index]) {
        resolveContradictions.push([question.field, question.secondary_field]);
      }
    });

    const response = await run(() =>
      applyAnswers(handoff, collectedAnswers, resolveContradictions),
    );
    if (response) {
      onApplied(response);
    }
  }

  return (
    <div className="clarification">
      <h3 className="section-title">Almost ready.</h3>
      <p className="muted">
        Answer what you can to complete the handoff. These prompts come from the
        analysis.
      </p>

      {questions.map((question, index) => (
        <QuestionBlock
          key={`${question.field}-${index}`}
          question={question}
          index={index}
          answer={answers[question.field] ?? ""}
          resolveChosen={Boolean(resolved[index])}
          onAnswer={(value) => setAnswer(question.field, value)}
          onToggleResolve={() => toggleResolve(index)}
        />
      ))}

      {status === "error" && (
        <ErrorBanner message={toUserMessage(error)} onRetry={handleApply} />
      )}

      <div className="button-row">
        <button
          type="button"
          className="primary"
          onClick={handleApply}
          disabled={isLoading}
        >
          Apply answers
        </button>
        <button type="button" onClick={onCancel} disabled={isLoading}>
          Cancel
        </button>
        {isLoading && <Spinner label="Applying…" />}
      </div>
    </div>
  );
}

interface QuestionBlockProps {
  question: Question;
  index: number;
  answer: string;
  resolveChosen: boolean;
  onAnswer: (value: string) => void;
  onToggleResolve: () => void;
}

function QuestionBlock({
  question,
  index,
  answer,
  resolveChosen,
  onAnswer,
  onToggleResolve,
}: QuestionBlockProps) {
  const inputId = `question-${index}`;
  const resolveId = `resolve-${index}`;
  const isContradiction = question.secondary_field !== null;

  return (
    <div className="question">
      <label htmlFor={inputId} className="question-text">
        {question.text}
      </label>
      <input
        id={inputId}
        type="text"
        value={answer}
        onChange={(event) => onAnswer(event.target.value)}
      />
      {isContradiction && question.secondary_field && (
        <label htmlFor={resolveId} className="resolve-control">
          <input
            id={resolveId}
            type="checkbox"
            checked={resolveChosen}
            onChange={onToggleResolve}
          />
          Mark the conflict between {FIELD_LABELS[question.field]} and{" "}
          {FIELD_LABELS[question.secondary_field]} as resolved
        </label>
      )}
    </div>
  );
}

export default ClarificationView;
