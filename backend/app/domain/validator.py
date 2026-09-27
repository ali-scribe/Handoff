"""Deterministic readiness validator: the pure validate_handoff function (no AI, no I/O)."""

from app.domain.handoff import (
    FieldCondition,
    HandoffFieldName,
    StructuredHandoff,
)
from app.domain.validation import (
    Issue,
    IssueSeverity,
    IssueType,
    ReadinessState,
    ValidationResult,
)

# --- Required-fields policy (design.md "Deterministic Rules" → "Required-fields
# policy"; Req 4.11, 4.12) ------------------------------------------------------
#
# Requiredness is decided by a fixed, deterministic policy — no AI, no inference.
# A field is required for the task if it is in ALWAYS_REQUIRED, or if it belongs
# to REQUIRED_UNLESS_NOT_APPLICABLE and its condition is not NOT_APPLICABLE.
# Every other field (deadline, context, constraints) is optional and never
# required. NOT_APPLICABLE is the single, explicit lever a caller uses to say
# "this field genuinely does not apply", which short-circuits any later
# missing-information issue for that field.

# objective and expected_output are the core of any handoff (always required).
ALWAYS_REQUIRED: frozenset[HandoffFieldName] = frozenset(
    {
        HandoffFieldName.OBJECTIVE,
        HandoffFieldName.EXPECTED_OUTPUT,
    }
)

# These are required unless the caller explicitly marks them NOT_APPLICABLE.
REQUIRED_UNLESS_NOT_APPLICABLE: frozenset[HandoffFieldName] = frozenset(
    {
        HandoffFieldName.INPUTS,
        HandoffFieldName.OWNER,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        HandoffFieldName.DEPENDENCIES,
    }
)

# deadline, context, and constraints are implicitly optional: they appear in
# neither set above, so is_field_required always returns False for them.


def _condition_of(
    handoff: StructuredHandoff, field_name: HandoffFieldName
) -> FieldCondition:
    """Return the FieldCondition of ``field_name`` on ``handoff`` (pure lookup).

    Uses the enum's string value (which matches the StructuredHandoff attribute
    name) to fetch the corresponding HandoffField and read its condition. No
    inference, no I/O.
    """
    return getattr(handoff, field_name.value).condition


def is_field_required(
    handoff: StructuredHandoff, field_name: HandoffFieldName
) -> bool:
    """Decide, deterministically, whether ``field_name`` is required for the task.

    Encodes the design's required-fields policy table and the two false-positive
    guards it exists to enforce:

    - A field marked ``NOT_APPLICABLE`` is never required, so it can never yield
      a missing-information issue later (Req 4.11).
    - Fields that are not required (optional fields, or those marked
      NOT_APPLICABLE) return ``False`` here, so later tasks will not raise a
      CRITICAL issue for such a field merely because it is absent (Req 4.12).

    This function is pure and deterministic: identical inputs always produce an
    identical result, with no side effects.
    """
    if field_name in ALWAYS_REQUIRED:
        return True
    if field_name in REQUIRED_UNLESS_NOT_APPLICABLE:
        return _condition_of(handoff, field_name) is not FieldCondition.NOT_APPLICABLE
    return False


# --- Issue detection (design.md "Deterministic Rules" → "Issue-detection
# rules" table; Req 4.1–4.10, 5.2–5.4, 6.3) ------------------------------------
#
# Each rule inspects one field's condition and, when its trigger holds, appends
# EXACTLY ONE Issue with the mapped IssueType/IssueSeverity and a concise,
# human-readable explanation (Req 6.3). Rules 3, 6, 7, and 9 only fire when the
# field is required per the 5.1 policy — this enforces the false-positive
# guards: a NOT_APPLICABLE field is never required so it yields no issue (Req
# 4.11), and a non-required MISSING field never yields a CRITICAL (Req 4.12).
#
# Contradiction detection (rule 8) is intentionally NOT implemented here — it is
# Task 5.3, which will scan handoff.contradictions and append
# contradictory_information issues before readiness is derived.


def _detect_issues(handoff: StructuredHandoff) -> list[Issue]:
    """Apply the deterministic issue-detection rules and return the issue list.

    Pure and deterministic: it reads only the given handoff's field conditions
    (via the required-fields policy helpers) and performs no I/O or inference.
    Rule numbers below match the design's issue-detection table.
    """
    issues: list[Issue] = []

    objective = _condition_of(handoff, HandoffFieldName.OBJECTIVE)
    expected_output = _condition_of(handoff, HandoffFieldName.EXPECTED_OUTPUT)
    inputs = _condition_of(handoff, HandoffFieldName.INPUTS)
    deadline = _condition_of(handoff, HandoffFieldName.DEADLINE)
    acceptance_criteria = _condition_of(handoff, HandoffFieldName.ACCEPTANCE_CRITERIA)
    dependencies = _condition_of(handoff, HandoffFieldName.DEPENDENCIES)
    owner = _condition_of(handoff, HandoffFieldName.OWNER)

    # Rule 1: objective MISSING -> missing_objective / CRITICAL (Req 4.1, 5.2).
    # MISSING is not AMBIGUOUS, so rule 1 and rule 2 never both fire.
    if objective is FieldCondition.MISSING:
        issues.append(
            Issue(
                issue_type=IssueType.MISSING_OBJECTIVE,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.OBJECTIVE,
                explanation=(
                    "The objective is missing; without a stated goal the work "
                    "cannot be executed."
                ),
            )
        )

    # Rule 2: objective AMBIGUOUS -> vague_objective / IMPORTANT (Req 4.2, 5.3).
    if objective is FieldCondition.AMBIGUOUS:
        issues.append(
            Issue(
                issue_type=IssueType.VAGUE_OBJECTIVE,
                severity=IssueSeverity.IMPORTANT,
                field=HandoffFieldName.OBJECTIVE,
                explanation=(
                    "The objective is vague or under-specified and should be "
                    "clarified before the work is attempted."
                ),
            )
        )

    # Rule 3: inputs MISSING and required -> missing_required_input / CRITICAL
    # (Req 4.3, 5.2). Guarded by the required-fields policy (Req 4.11, 4.12).
    if inputs is FieldCondition.MISSING and is_field_required(
        handoff, HandoffFieldName.INPUTS
    ):
        issues.append(
            Issue(
                issue_type=IssueType.MISSING_REQUIRED_INPUT,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.INPUTS,
                explanation=(
                    "A required input is missing; the work cannot proceed "
                    "without it."
                ),
            )
        )

    # Rule 4: expected_output MISSING -> missing_expected_output / CRITICAL
    # (Req 4.4, 5.2).
    if expected_output is FieldCondition.MISSING:
        issues.append(
            Issue(
                issue_type=IssueType.MISSING_EXPECTED_OUTPUT,
                severity=IssueSeverity.CRITICAL,
                field=HandoffFieldName.EXPECTED_OUTPUT,
                explanation=(
                    "The expected output is missing; there is no way to know "
                    "what a finished result should look like."
                ),
            )
        )

    # Rule 5: deadline AMBIGUOUS -> vague_deadline / IMPORTANT (Req 4.5, 5.3).
    if deadline is FieldCondition.AMBIGUOUS:
        issues.append(
            Issue(
                issue_type=IssueType.VAGUE_DEADLINE,
                severity=IssueSeverity.IMPORTANT,
                field=HandoffFieldName.DEADLINE,
                explanation=(
                    "The deadline is vague; a specific date or time should be "
                    "confirmed."
                ),
            )
        )

    # Rule 6: acceptance_criteria MISSING and required ->
    # missing_acceptance_criteria / IMPORTANT (Req 4.6, 5.3). Guarded by policy.
    if acceptance_criteria is FieldCondition.MISSING and is_field_required(
        handoff, HandoffFieldName.ACCEPTANCE_CRITERIA
    ):
        issues.append(
            Issue(
                issue_type=IssueType.MISSING_ACCEPTANCE_CRITERIA,
                severity=IssueSeverity.IMPORTANT,
                field=HandoffFieldName.ACCEPTANCE_CRITERIA,
                explanation=(
                    "Acceptance criteria are missing; there is no agreed "
                    "definition of done to check the result against."
                ),
            )
        )

    # Rule 7: dependencies MISSING or AMBIGUOUS and required ->
    # unresolved_dependency / IMPORTANT (Req 4.7, 5.3). Guarded by policy.
    if dependencies in (
        FieldCondition.MISSING,
        FieldCondition.AMBIGUOUS,
    ) and is_field_required(handoff, HandoffFieldName.DEPENDENCIES):
        issues.append(
            Issue(
                issue_type=IssueType.UNRESOLVED_DEPENDENCY,
                severity=IssueSeverity.IMPORTANT,
                field=HandoffFieldName.DEPENDENCIES,
                explanation=(
                    "A dependency is unresolved (missing or unclear) and should "
                    "be settled before the work starts."
                ),
            )
        )

    # Rule 8 (declared contradictions -> contradictory_information / CRITICAL) is
    # intentionally NOT handled here. Contradiction reporting lives in
    # _detect_contradictions, which validate_handoff calls separately. This keeps
    # _detect_issues focused on single-field condition rules.

    # Rule 9: owner MISSING or AMBIGUOUS and required -> ambiguous_ownership /
    # IMPORTANT (Req 4.9, 5.3). Guarded by policy.
    if owner in (
        FieldCondition.MISSING,
        FieldCondition.AMBIGUOUS,
    ) and is_field_required(handoff, HandoffFieldName.OWNER):
        issues.append(
            Issue(
                issue_type=IssueType.AMBIGUOUS_OWNERSHIP,
                severity=IssueSeverity.IMPORTANT,
                field=HandoffFieldName.OWNER,
                explanation=(
                    "Ownership is unclear; the person responsible for the work "
                    "needs to be identified."
                ),
            )
        )

    # Rule 10: objective or expected_output AMBIGUOUS -> vague_action_language /
    # MINOR, one issue per ambiguous field (Req 4.10, 5.4). This co-fires with
    # rule 2 on an AMBIGUOUS objective — that is intended (two distinct types).
    if objective is FieldCondition.AMBIGUOUS:
        issues.append(
            Issue(
                issue_type=IssueType.VAGUE_ACTION_LANGUAGE,
                severity=IssueSeverity.MINOR,
                field=HandoffFieldName.OBJECTIVE,
                explanation=(
                    "The objective uses vague action language; more concrete "
                    "wording would make the intended work clearer."
                ),
            )
        )
    if expected_output is FieldCondition.AMBIGUOUS:
        issues.append(
            Issue(
                issue_type=IssueType.VAGUE_ACTION_LANGUAGE,
                severity=IssueSeverity.MINOR,
                field=HandoffFieldName.EXPECTED_OUTPUT,
                explanation=(
                    "The expected output uses vague action language; more "
                    "concrete wording would make the target clearer."
                ),
            )
        )

    return issues


# --- Contradiction detection (design.md "Deterministic Rules" → "Contradiction
# detection (Req 4.8)"; Req 4.8, 5.2) -----------------------------------------
#
# Contradictions are *declared, not discovered*. The validator performs no NLP
# and never inspects raw field text to infer conflicts; it only reports the
# (field_a, field_b) pairs a producer has explicitly declared on
# handoff.contradictions. Those pairs will eventually be supplied by an upstream
# extraction layer (out of scope here) that populates the list; the validator's
# contract is unchanged. This keeps contradiction handling deterministic and
# testable for a solo-student-maintainable, AI-free core.


def _detect_contradictions(handoff: StructuredHandoff) -> list[Issue]:
    """Report declared contradictions as issues (pure, deterministic; Req 4.8, 5.2).

    For EACH (field_a, field_b) pair declared on ``handoff.contradictions``,
    append EXACTLY ONE CRITICAL contradictory_information Issue with
    ``field=field_a`` and ``secondary_field=field_b``. Order follows the declared
    list, so the output is deterministic and stable. This does not discover
    contradictions from field values — it only faithfully reports declared ones.
    """
    issues: list[Issue] = []
    for field_a, field_b in handoff.contradictions:
        issues.append(
            Issue(
                issue_type=IssueType.CONTRADICTORY_INFORMATION,
                severity=IssueSeverity.CRITICAL,
                field=field_a,
                secondary_field=field_b,
                explanation=(
                    f"The '{field_a.value}' and '{field_b.value}' fields contain "
                    "contradictory information that must be reconciled."
                ),
            )
        )
    return issues


# --- Readiness derivation (design.md "Deterministic Rules" → "Readiness
# derivation (Req 3.3–3.7)"; Req 3.3–3.6, 5.5) --------------------------------


def _derive_readiness(issues: list[Issue]) -> ReadinessState:
    """Reduce an issue list to a single readiness verdict (pure, deterministic).

    Exact rule from the design (Req 3.3–3.6, 5.5):

    - any CRITICAL issue      -> NOT_READY             (Req 3.3)
    - else any IMPORTANT issue -> NEEDS_CLARIFICATION  (Req 3.4)
    - otherwise                -> READY                (Req 3.5, 3.6, 5.5)

    The final branch covers both an only-MINOR issue set and an empty one:
    MINOR issues are non-blocking, so they never reduce readiness below READY
    (Req 5.5). This is a pure function of ``issues`` — no I/O, no inference.
    """
    if any(issue.severity is IssueSeverity.CRITICAL for issue in issues):
        return ReadinessState.NOT_READY
    if any(issue.severity is IssueSeverity.IMPORTANT for issue in issues):
        return ReadinessState.NEEDS_CLARIFICATION
    return ReadinessState.READY


def validate_handoff(handoff: StructuredHandoff) -> ValidationResult:
    """Deterministically decide readiness for a handoff. PURE: no I/O, no AI, no network.

    Given identical input, this returns an equal ValidationResult on every call,
    so validation is idempotent/deterministic (Req 3.2, 3.7, 3.8, 4.13). It
    composes three pure, order-stable helpers — issue detection, declared
    contradictions, and readiness derivation — with no side effects. The domain
    models are frozen, so an input handoff cannot mutate between runs, which
    reinforces this determinism.
    """
    # Field-condition issues first, then declared-contradiction issues. Both
    # helpers are pure and order-stable, so the combined list is deterministic.
    # A declared contradiction is CRITICAL, so its presence reduces readiness to
    # NOT_READY.
    issues = _detect_issues(handoff) + _detect_contradictions(handoff)

    readiness = _derive_readiness(issues)

    return ValidationResult(readiness_state=readiness, issues=issues)
