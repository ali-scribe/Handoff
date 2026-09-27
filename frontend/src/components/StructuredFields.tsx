import {
  FIELD_LABELS,
  HANDOFF_FIELD_ORDER,
  type HandoffField,
  type HandoffFieldName,
  type StructuredHandoff,
  type ValidationResult,
} from "../types/handoff";

/**
 * Render the value/condition of one field.
 *
 * The distinction between present, missing, ambiguous, and not-applicable comes
 * entirely from the backend ``condition``. For a MISSING field, whether it is
 * shown with attention styling ("Missing") or neutral styling ("Not provided")
 * is decided ONLY by ``flagged`` — i.e. whether the backend raised an issue for
 * this field in ``validation.issues``. The frontend never reproduces the
 * backend's required/optional policy and never computes readiness.
 */
function FieldValue({
  field,
  flagged,
}: {
  field: HandoffField;
  flagged: boolean;
}) {
  switch (field.condition) {
    case "missing":
      // Required-missing (the backend flagged it) => attention. Otherwise the
      // field is optional for this handoff => neutral, non-error presentation.
      return flagged ? (
        <span className="field-marker">Missing</span>
      ) : (
        <span>
          <span className="field-marker">Not provided</span>
          <span className="field-optional-note">
            Optional — this won't block the handoff.
          </span>
        </span>
      );
    case "not_applicable":
      return (
        <span>
          <span className="field-marker">Not provided</span>
          <span className="field-optional-note">
            Not applicable — this won't block the handoff.
          </span>
        </span>
      );
    case "ambiguous":
      return (
        <span>
          <span className="field-marker">Unclear: </span>
          {renderValue(field.value)}
        </span>
      );
    case "present":
    default:
      return <span className="field-value">{renderValue(field.value)}</span>;
  }
}

/** Render a scalar or list value. Lists become a bulleted list; null shows nothing. */
function renderValue(value: string | string[] | null) {
  if (value === null) return null;
  if (Array.isArray(value)) {
    return (
      <span className="field-value">
        <ul>
          {value.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </span>
    );
  }
  return value;
}

interface StructuredFieldsProps {
  handoff: StructuredHandoff;
  validation: ValidationResult;
}

/**
 * Render all nine structured fields in the backend's canonical order.
 *
 * A field is presented with attention styling only when the backend itself
 * flagged it: its name appears as ``field`` or ``secondary_field`` on some entry
 * of ``validation.issues``. This is a purely presentational read of the
 * backend's own verdict — no requiredness rule and no readiness logic is
 * reproduced here. The backend remains the sole authority.
 */
function StructuredFields({ handoff, validation }: StructuredFieldsProps) {
  const flaggedFields = new Set<HandoffFieldName>();
  for (const issue of validation.issues) {
    flaggedFields.add(issue.field);
    if (issue.secondary_field) {
      flaggedFields.add(issue.secondary_field);
    }
  }

  return (
    <div className="fields">
      {HANDOFF_FIELD_ORDER.map((name: HandoffFieldName) => {
        const field = handoff[name];
        const flagged = flaggedFields.has(name);
        const optionalMissing = field.condition === "missing" && !flagged;
        return (
          <div
            className="field"
            key={name}
            data-condition={field.condition}
            data-optional-missing={optionalMissing ? "true" : undefined}
          >
            <div className="field-label">{FIELD_LABELS[name]}</div>
            <FieldValue field={field} flagged={flagged} />
          </div>
        );
      })}
    </div>
  );
}

export default StructuredFields;
