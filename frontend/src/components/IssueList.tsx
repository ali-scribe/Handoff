import {
  FIELD_LABELS,
  type Issue,
  type IssueSeverity,
} from "../types/handoff";

/** Severity groups in display order, with human labels. */
const SEVERITY_ORDER: { severity: IssueSeverity; label: string }[] = [
  { severity: "critical", label: "Critical" },
  { severity: "important", label: "Important" },
  { severity: "minor", label: "Minor" },
];

interface IssueListProps {
  issues: Issue[];
}

/**
 * Render backend-provided issues grouped by their backend severity. Purely
 * presentational: no severity or classification is computed here. Each issue
 * shows its severity chip, explanation, and affected field(s).
 */
function IssueList({ issues }: IssueListProps) {
  if (issues.length === 0) {
    return <p className="muted">No issues found.</p>;
  }

  return (
    <div>
      {SEVERITY_ORDER.map(({ severity, label }) => {
        const group = issues.filter((issue) => issue.severity === severity);
        if (group.length === 0) return null;
        return (
          <div className="issue-group" key={severity}>
            <h4 className="issue-group-title">{label}</h4>
            {group.map((issue, index) => (
              <IssueRow
                key={`${issue.issue_type}-${issue.field}-${index}`}
                issue={issue}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function IssueRow({ issue }: { issue: Issue }) {
  const fieldLabel = FIELD_LABELS[issue.field];
  const affected = issue.secondary_field
    ? `${fieldLabel} + ${FIELD_LABELS[issue.secondary_field]}`
    : fieldLabel;

  return (
    <div className="issue" data-severity={issue.severity}>
      <span className="severity-chip" data-severity={issue.severity}>
        {issue.severity}
      </span>
      <span>{issue.explanation}</span>
      <div className="issue-field">Field: {affected}</div>
    </div>
  );
}

export default IssueList;
