import { DEMO_EXAMPLES } from "../data/demoExamples";

interface DemoExamplesProps {
  /** Called with the example's text when a user picks one. */
  onSelect: (text: string) => void;
  /** Disable selection while an analysis is in flight. */
  disabled?: boolean;
}

/**
 * A small, secondary "Try an example" section shown under the input. Each item
 * loads a pre-baked request into the existing textarea via onSelect — it never
 * submits/analyzes, and the text stays fully editable afterward. Purely
 * presentational: the example text lives in ../data/demoExamples and the
 * textarea state stays in InputView.
 */
function DemoExamples({ onSelect, disabled = false }: DemoExamplesProps) {
  return (
    <section className="demo-examples" aria-labelledby="demo-examples-title">
      <h3 id="demo-examples-title" className="demo-examples-title">
        Try an example
      </h3>
      <div className="demo-examples-list">
        {DEMO_EXAMPLES.map((example) => (
          <button
            key={example.id}
            type="button"
            className="demo-example"
            onClick={() => onSelect(example.text)}
            disabled={disabled}
            aria-label={`Load example: ${example.title} — ${example.description}`}
          >
            <span className="demo-example-title">{example.title}</span>
            <span className="demo-example-desc">{example.description}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

export default DemoExamples;
