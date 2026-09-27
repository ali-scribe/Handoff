/**
 * ProcessFlow — a quiet, decorative process indicator.
 *
 * Renders four connected nodes representing the Handoff pipeline:
 *   Input → Analyze/Results → Clarify → Ready
 *
 * It is purely presentational: it consumes the `stage` the app already knows
 * (derived from App's existing phase state) and never computes readiness or any
 * domain state. Node/line activation is driven entirely by CSS via the
 * `data-stage` attribute and each node's `data-index`, so state changes are
 * simple CSS transitions with no animation loop. aria-hidden and
 * pointer-events:none (see index.css) — it is secondary to all content.
 */

export type ProcessStage = "input" | "results" | "clarifying" | "ready";

/** Zero-based index of the active node for each stage. */
const STAGE_INDEX: Record<ProcessStage, number> = {
  input: 0,
  results: 1,
  clarifying: 2,
  ready: 3,
};

const NODES: { label: string; cx: number }[] = [
  { label: "Input", cx: 40 },
  { label: "Results", cx: 200 },
  { label: "Clarify", cx: 360 },
  { label: "Ready", cx: 520 },
];

interface ProcessFlowProps {
  stage: ProcessStage;
}

function ProcessFlow({ stage }: ProcessFlowProps) {
  const activeIndex = STAGE_INDEX[stage];

  return (
    <div className="process-flow" data-stage={stage} aria-hidden="true">
      <svg
        className="process-flow-svg"
        viewBox="0 0 560 60"
        role="presentation"
        focusable="false"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Connecting segments between consecutive nodes. A segment is
            "complete" when the stage has advanced past its start node. */}
        <g className="process-lines">
          {NODES.slice(0, -1).map((node, i) => (
            <line
              key={i}
              className="process-line"
              data-complete={activeIndex > i ? "true" : undefined}
              x1={node.cx}
              y1={30}
              x2={NODES[i + 1].cx}
              y2={30}
            />
          ))}
        </g>

        {/* Nodes. Each is muted, "completed" (softly lit), or "active". */}
        <g className="process-nodes">
          {NODES.map((node, i) => {
            const state =
              i === activeIndex
                ? "active"
                : i < activeIndex
                  ? "complete"
                  : "muted";
            return (
              <circle
                key={node.label}
                className="process-node"
                data-node-state={state}
                data-final={i === NODES.length - 1 ? "true" : undefined}
                cx={node.cx}
                cy={30}
                r={7}
              />
            );
          })}
        </g>
      </svg>
    </div>
  );
}

export default ProcessFlow;
