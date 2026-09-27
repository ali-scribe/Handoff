"""Deterministic clarification-question generation (pure: no I/O, no AI, no web framework).

Given a ValidationResult (produced by the sole readiness authority in the
domain), this module turns detected issues into a small, prioritized list of clarifying
questions. It NEVER computes readiness or recomputes severity: it only reads the
severity already attached to each Issue to order and dedupe questions. It never
asks about fields that produced no issue (PRESENT / NOT_APPLICABLE / clean
optional fields), which is automatic since those never appear in the issue list.
"""

from pydantic import BaseModel, ConfigDict

from app.domain.handoff import HandoffFieldName
from app.domain.validation import IssueSeverity, IssueType, ValidationResult


class Question(BaseModel):
    """One clarifying question targeting a single handoff field (frozen DTO).

    ``field`` is the primary field the question is about. ``secondary_field`` is
    populated only for contradiction questions (the second conflicting field).
    ``issue_types`` accumulates every issue type merged into this question for
    that field, in first-seen order. ``text`` is the deterministic prompt.
    """

    field: HandoffFieldName
    secondary_field: HandoffFieldName | None = None
    issue_types: tuple[IssueType, ...]
    text: str

    model_config = ConfigDict(frozen=True)


# Explicit, deterministic question template per IssueType. Contradiction and the
# field-specific vague_action_language template use ``.format(...)`` with the
# relevant field value names; the rest are fixed strings.
_TEMPLATES: dict[IssueType, str] = {
    IssueType.MISSING_OBJECTIVE: (
        "What is the objective of this work? Describe the goal to be achieved."
    ),
    IssueType.VAGUE_OBJECTIVE: (
        "The objective is unclear. Can you state the objective more specifically?"
    ),
    IssueType.VAGUE_ACTION_LANGUAGE: (
        "The wording is vague. Can you describe the intended action in concrete "
        "terms for the {field} field?"
    ),
    IssueType.MISSING_REQUIRED_INPUT: (
        "What inputs are required to do this work? List the inputs needed."
    ),
    IssueType.MISSING_EXPECTED_OUTPUT: (
        "What is the expected output or deliverable?"
    ),
    IssueType.VAGUE_DEADLINE: (
        "When is this due? Please give a specific date or time."
    ),
    IssueType.MISSING_ACCEPTANCE_CRITERIA: (
        "How will we know the work is done correctly? List the acceptance criteria."
    ),
    IssueType.UNRESOLVED_DEPENDENCY: (
        "What does this work depend on? List any dependencies (or state there "
        "are none)."
    ),
    IssueType.AMBIGUOUS_OWNERSHIP: (
        "Who is responsible for doing this work?"
    ),
    IssueType.CONTRADICTORY_INFORMATION: (
        "The '{field}' and '{secondary_field}' fields appear to conflict. Which "
        "is correct, or how should they be reconciled?"
    ),
}

# Severity ordering: CRITICAL first, then IMPORTANT, then MINOR. Lower rank sorts
# earlier.
_SEVERITY_RANK: dict[IssueSeverity, int] = {
    IssueSeverity.CRITICAL: 0,
    IssueSeverity.IMPORTANT: 1,
    IssueSeverity.MINOR: 2,
}

# HandoffFieldName declaration order, used as the deterministic tie-break.
_FIELD_ORDER: dict[HandoffFieldName, int] = {
    name: index for index, name in enumerate(HandoffFieldName)
}

# Maximum number of questions ever returned.
_MAX_QUESTIONS = 5


def _render_text(
    issue_type: IssueType,
    field: HandoffFieldName,
    secondary_field: HandoffFieldName | None,
) -> str:
    """Render the template for ``issue_type``, filling field value names.

    ``.format`` is safe here: every template is a literal in ``_TEMPLATES`` and
    the only substituted values are enum ``.value`` strings.
    """
    template = _TEMPLATES[issue_type]
    return template.format(
        field=field.value,
        secondary_field=secondary_field.value if secondary_field is not None else "",
    )


def generate_questions(validation: ValidationResult) -> list[Question]:
    """Turn a ValidationResult into a prioritized, deduped list of Questions.

    Deterministic algorithm (pure; no readiness/severity derivation):

    1. Iterate ``validation.issues`` in order, grouping by PRIMARY field. At most
       one question per field. For each field we accumulate its issue types
       (deduped, first-seen order) and remember the highest-severity issue seen
       for that field (that issue supplies the question text; ties keep the
       first-seen issue).
    2. Contradiction issues always use the contradiction template and carry the
       ``secondary_field``.
    3. Order the per-field questions by max severity (CRITICAL, IMPORTANT,
       MINOR), tie-broken by HandoffFieldName declaration order.
    4. Return at most five questions.

    Empty issues -> ``[]``.
    """
    # Per-field accumulator, keyed by primary field, preserving first-seen order.
    # Each entry tracks: ordered unique issue types, the best (highest-severity)
    # issue for text selection, and that issue's severity + secondary field.
    grouped: dict[HandoffFieldName, dict] = {}

    for issue in validation.issues:
        field = issue.field
        if field not in grouped:
            grouped[field] = {
                "issue_types": [],
                "best_issue_type": issue.issue_type,
                "best_severity": issue.severity,
                "secondary_field": issue.secondary_field,
            }
        entry = grouped[field]

        if issue.issue_type not in entry["issue_types"]:
            entry["issue_types"].append(issue.issue_type)

        # A contradiction always dictates the template + secondary field for the
        # question, regardless of severity ranking among same-field issues.
        if issue.issue_type is IssueType.CONTRADICTORY_INFORMATION:
            entry["best_issue_type"] = IssueType.CONTRADICTORY_INFORMATION
            entry["best_severity"] = issue.severity
            entry["secondary_field"] = issue.secondary_field
            continue

        # Otherwise pick the strictly-higher-severity issue's type for the text.
        # Strict comparison keeps the first-seen issue on ties.
        if _SEVERITY_RANK[issue.severity] < _SEVERITY_RANK[entry["best_severity"]]:
            entry["best_issue_type"] = issue.issue_type
            entry["best_severity"] = issue.severity

    questions: list[tuple[int, int, Question]] = []
    for field, entry in grouped.items():
        secondary = entry["secondary_field"]
        text = _render_text(entry["best_issue_type"], field, secondary)
        question = Question(
            field=field,
            secondary_field=secondary,
            issue_types=tuple(entry["issue_types"]),
            text=text,
        )
        sort_key = (_SEVERITY_RANK[entry["best_severity"]], _FIELD_ORDER[field])
        questions.append((sort_key[0], sort_key[1], question))

    # Prioritize: severity rank first, then field declaration order.
    questions.sort(key=lambda item: (item[0], item[1]))

    return [q for _, _, q in questions][:_MAX_QUESTIONS]
