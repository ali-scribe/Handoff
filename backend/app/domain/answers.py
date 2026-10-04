"""Deterministic answer application + contradiction resolution (pure: no I/O, no AI, no web framework).

Applying an answer replaces a single target field's value and assigns its
FieldCondition. Most answers are accepted as PRESENT. Fields with a clear
semantic type (currently the deadline) additionally require the answer to look
like that type: an answer that plainly does not — e.g. a person's name given
for a deadline — is marked AMBIGUOUS, not PRESENT, so a non-empty-but-wrong
answer cannot silently satisfy the field. This condition assignment is the only
semantic judgment made here; readiness and severity remain the sole
responsibility of the deterministic validator, which a caller runs separately
after these transformations.

Resolving a contradiction removes exactly one declared (field_a, field_b) pair.
All functions are pure and operate on frozen domain models via ``model_copy``.
"""

import re

from pydantic import BaseModel, ConfigDict

from app.domain.handoff import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    StructuredHandoff,
)


class Answer(BaseModel):
    """A user's answer to a clarifying question: the target field + raw value (frozen)."""

    field: HandoffFieldName
    value: str

    model_config = ConfigDict(frozen=True)


class ClarificationError(Exception):
    """Base error for the clarification feature (answer application / resolution)."""


class EmptyAnswerError(ClarificationError):
    """Raised when an answer contains no usable content after normalization."""


class InvalidTargetFieldError(ClarificationError):
    """Raised when an answer targets something that is not one of the nine fields."""


class ContradictionNotFoundError(ClarificationError):
    """Raised when the exact contradiction pair to resolve is not declared."""


# The four list-valued fields and the five scalar fields. Together exhaustive
# over the nine HandoffFieldName members.
LIST_VALUED_FIELDS: frozenset[HandoffFieldName] = frozenset(
    {
        HandoffFieldName.INPUTS,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        HandoffFieldName.CONSTRAINTS,
        HandoffFieldName.DEPENDENCIES,
    }
)

SCALAR_FIELDS: frozenset[HandoffFieldName] = frozenset(
    {
        HandoffFieldName.OBJECTIVE,
        HandoffFieldName.OWNER,
        HandoffFieldName.EXPECTED_OUTPUT,
        HandoffFieldName.DEADLINE,
        HandoffFieldName.CONTEXT,
    }
)


# --- Deterministic deadline recognition -------------------------------------
#
# A deadline answer must carry some date/time signal; otherwise an arbitrary
# string (e.g. a person's name) would wrongly satisfy the field. This is a
# conservative, deterministic check: it recognizes common ways people express a
# time/date and, crucially, errs toward ACCEPTING anything time-like so valid
# deadlines are never rejected. No AI, no parsing of real calendars.

_MONTHS = (
    "january february march april may june july august september october "
    "november december jan feb mar apr jun jul aug sep sept oct nov dec"
).split()

_WEEKDAYS = (
    "monday tuesday wednesday thursday friday saturday sunday "
    "mon tue tues wed thu thur thurs fri sat sun"
).split()

# Relative / colloquial time words and phrases.
_RELATIVE_TIME_TERMS = (
    "today",
    "tonight",
    "tomorrow",
    "yesterday",
    "noon",
    "midnight",
    "eod",
    "eow",
    "cob",
    "asap",
    "now",
    "week",
    "weeks",
    "day",
    "days",
    "month",
    "months",
    "year",
    "years",
    "hour",
    "hours",
    "minute",
    "minutes",
    "morning",
    "afternoon",
    "evening",
    "quarter",
    "end of",
    "by the end",
    "next ",
    "this ",
    "coming ",
)

# Structured date/time patterns: numeric dates (1/2, 1-2, ISO), times (3pm,
# 15:30), ISO datetimes, quarter labels (Q1), and year numbers (2020-2099).
_DATE_TIME_PATTERNS = (
    re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b"),         # 2025-03-01 (ISO date)
    re.compile(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b"),  # 3/1, 03-01-2025
    re.compile(r"\b\d{1,2}:\d{2}\b"),                  # 15:30
    re.compile(r"\b\d{1,2}\s?(am|pm)\b", re.IGNORECASE),  # 3pm, 3 pm
    re.compile(r"\bq[1-4]\b", re.IGNORECASE),          # Q1..Q4
    re.compile(r"\b(19|20)\d{2}\b"),                   # a 4-digit year
    re.compile(r"\b\d{1,2}(st|nd|rd|th)\b", re.IGNORECASE),  # 1st, 2nd, 15th
)


def _looks_like_deadline(value: str) -> bool:
    """True if ``value`` carries any recognizable date/time signal (deterministic).

    Conservative by design: it recognizes structured dates/times, month and
    weekday names, and common relative/colloquial time terms. It errs toward
    acceptance so legitimate deadlines are never rejected; it returns False only
    when the answer contains no time signal at all (e.g. a bare name).
    """
    lowered = value.lower()

    for pattern in _DATE_TIME_PATTERNS:
        if pattern.search(value):
            return True

    # Word-boundary matches for month / weekday names.
    words = set(re.findall(r"[a-z]+", lowered))
    if words & set(_MONTHS):
        return True
    if words & set(_WEEKDAYS):
        return True

    # Relative / colloquial terms (substring is fine for multi-word phrases).
    if any(term in lowered for term in _RELATIVE_TIME_TERMS):
        return True

    return False


# --- Conservative "has substance" check for description-type fields ---------
#
# expected_output, acceptance_criteria, and dependencies all expect a DESCRIPTION
# of something (a deliverable, a criterion for acceptance, an external
# prerequisite). A lone bare word — e.g. a person's name typed in by mistake,
# "Ali" — is not a usable description and must not silently satisfy the field.
#
# The check is intentionally type-agnostic and uses NO name/keyword lists: a
# single whitespace-delimited, purely-alphabetic token has no descriptive
# substance. Anything with more than one word, or any digit/punctuation
# (identifiers like "service-x", "v2", "data.csv", URLs, versions), is accepted
# as before. This errs toward acceptance: it only rejects the clearest case
# (one bare word), preserving all legitimate free-form answers.

# Fields whose answers must describe something, so a lone bare word is invalid.
_DESCRIPTION_FIELDS: frozenset[HandoffFieldName] = frozenset(
    {
        HandoffFieldName.EXPECTED_OUTPUT,
        HandoffFieldName.ACCEPTANCE_CRITERIA,
        HandoffFieldName.DEPENDENCIES,
    }
)


def _has_substance(item: str) -> bool:
    """True unless ``item`` is a single bare, purely-alphabetic word.

    Multiple words, or any non-letter character (digits, '-', '_', '/', '.',
    etc.), count as substance. Only a lone alphabetic token like "Ali" or "foo"
    is considered insufficient. Deterministic; no name/keyword lists.
    """
    stripped = item.strip()
    if " " in stripped or "\t" in stripped:
        return True
    return not stripped.isalpha()


# Standalone "no value" tokens: the whole answer is exactly one of these.
_NO_VALUE_TOKENS: frozenset[str] = frozenset({"none", "no", "n/a", "na", "nil"})

# A leading negation ("no"/"none"/"not") followed by a dependency-context word
# ("dependencies", "needed", "required", "prerequisites", ...). This recognizes
# the explicit "there are none" answer the dependencies clarification question
# invites — it is a narrow intent matcher for ONE field, not a blacklist of
# invalid tokens.
_NO_DEPENDENCY_PHRASE = re.compile(
    r"^(no|none|not)\b.*\b(depend\w*|need\w*|requir\w*|prereq\w*|extern\w*)",
    re.IGNORECASE,
)


def _is_no_dependency_answer(value: str) -> bool:
    """True if ``value`` explicitly states there are no dependencies.

    Matches a standalone no-value token ("none", "n/a", ...) or a leading
    negation phrase that refers to dependencies/needs ("none needed", "no
    dependencies", "no external dependencies"). Deterministic and scoped to the
    dependencies field only. A real dependency like "service-x" or an unrelated
    word like "Ali" does not match.
    """
    normalized = value.strip().lower()
    if normalized in _NO_VALUE_TOKENS:
        return True
    return bool(_NO_DEPENDENCY_PHRASE.match(normalized))


def _classify_condition(field: HandoffFieldName, value: str | list[str]) -> FieldCondition:
    """Decide the FieldCondition for a coerced answer value.

    Default is PRESENT (the user supplied content for the field). Two
    conservative semantic overrides mark an answer as unsatisfied so it cannot
    silently satisfy the field — the exact condition is chosen so the EXISTING
    validator (which this layer must not change) still flags the field:

    * DEADLINE with no date/time signal -> AMBIGUOUS. The validator's deadline
      rule triggers on AMBIGUOUS, so the vague_deadline issue persists.
    * EXPECTED_OUTPUT / ACCEPTANCE_CRITERIA / DEPENDENCIES answered with just a
      lone bare word (no descriptive substance) -> MISSING. The validator's
      rules for these fields trigger on MISSING (and, for dependencies, also
      AMBIGUOUS), so MISSING reliably keeps the field's issue in place. For the
      list-valued of these, the answer is insufficient only when EVERY item
      lacks substance.

    One positive override: a DEPENDENCIES answer that explicitly states there
    are no dependencies ("none", "none needed", "no external dependencies") ->
    NOT_APPLICABLE, a VALID no-dependency completion the clarification question
    invites. Checked before the substance rule so a lone "none" is accepted.

    All other fields (and any uncertain case) keep PRESENT, exactly as before.
    This function reads the validator's trigger conditions but does not modify
    them; readiness remains the validator's sole responsibility.
    """
    if field is HandoffFieldName.DEADLINE and isinstance(value, str):
        if not _looks_like_deadline(value):
            return FieldCondition.AMBIGUOUS

    if field is HandoffFieldName.DEPENDENCIES:
        # The dependencies clarification question explicitly invites "state there
        # are none". An explicit no-dependency answer is a VALID completion:
        # mark it NOT_APPLICABLE, which the validator treats as not-required (so
        # it satisfies the field) without any validator change. Checked before
        # the substance rule so a lone "none" is accepted rather than rejected.
        items = value if isinstance(value, list) else [value]
        if items and all(
            isinstance(item, str) and _is_no_dependency_answer(item) for item in items
        ):
            return FieldCondition.NOT_APPLICABLE

    if field in _DESCRIPTION_FIELDS:
        items = value if isinstance(value, list) else [value]
        # Insufficient only when nothing provided has substance (a list with at
        # least one substantive item is accepted).
        if items and not any(_has_substance(item) for item in items):
            return FieldCondition.MISSING

    return FieldCondition.PRESENT


def _coerce_value(field: HandoffFieldName, answer: str) -> str | list[str]:
    """Normalize a raw answer string into the shape the target field expects.

    List fields: split on newlines, strip each line, drop empties -> list[str];
    an empty result raises EmptyAnswerError. Scalar fields: strip; an empty
    result raises EmptyAnswerError. Pure.
    """
    if field in LIST_VALUED_FIELDS:
        items = [line.strip() for line in answer.split("\n")]
        items = [item for item in items if item != ""]
        if not items:
            raise EmptyAnswerError(
                f"The answer for '{field.value}' contained no usable list items."
            )
        return items

    stripped = answer.strip()
    if stripped == "":
        raise EmptyAnswerError(
            f"The answer for '{field.value}' was empty."
        )
    return stripped


def apply_answer(
    handoff: StructuredHandoff, field: HandoffFieldName, answer: str
) -> StructuredHandoff:
    """Return a copy of ``handoff`` with ``field`` set from ``answer``.

    The target field is overwritten regardless of its original condition (even
    PRESENT) with the coerced value and the condition from
    ``_classify_condition``. Normally that is PRESENT; two conservative
    overrides keep a non-empty-but-invalid answer from satisfying the field: a
    DEADLINE answer carrying no date/time signal becomes AMBIGUOUS, and an
    EXPECTED_OUTPUT / ACCEPTANCE_CRITERIA / DEPENDENCIES answer that is just a
    lone bare word becomes MISSING (its stored value is cleared to None). No
    other field is touched and ``contradictions`` is untouched. An empty answer
    raises EmptyAnswerError; a field that is not one of the nine raises
    InvalidTargetFieldError.
    """
    if not isinstance(field, HandoffFieldName) or field.value not in StructuredHandoff.model_fields:
        raise InvalidTargetFieldError(
            "The answer targeted a field that is not part of the handoff."
        )

    value = _coerce_value(field, answer)
    condition = _classify_condition(field, value)
    # A field marked MISSING carries no value, matching the domain convention
    # (MISSING => value is None). This keeps a rejected lone-word answer from
    # being persisted as if it were real content.
    stored_value = None if condition is FieldCondition.MISSING else value
    new_field = HandoffField(value=stored_value, condition=condition)
    return handoff.model_copy(update={field.value: new_field})


def apply_answers(
    handoff: StructuredHandoff, answers: list[Answer]
) -> StructuredHandoff:
    """Apply each answer in turn (fold-left); last write wins per field.

    Order-independent across distinct fields; for the same field the last answer
    wins. Never touches ``contradictions``. Typed errors from ``apply_answer``
    propagate.
    """
    updated = handoff
    for answer in answers:
        updated = apply_answer(updated, answer.field, answer.value)
    return updated


def resolve_contradiction(
    handoff: StructuredHandoff,
    field_a: HandoffFieldName,
    field_b: HandoffFieldName,
) -> StructuredHandoff:
    """Return a copy of ``handoff`` with the exact (field_a, field_b) pair removed.

    The match is exact and order-sensitive against ``handoff.contradictions``. If
    the pair is not present, raise ContradictionNotFoundError and leave the
    handoff unchanged. Only the matching pair is removed (if duplicates of the
    same pair exist, all equal occurrences are filtered out — documented
    behavior); every field value/condition and all other pairs are preserved.
    """
    pair = (field_a, field_b)
    if pair not in handoff.contradictions:
        raise ContradictionNotFoundError(
            "The specified contradiction pair was not declared on this handoff."
        )
    remaining = [p for p in handoff.contradictions if p != pair]
    return handoff.model_copy(update={"contradictions": remaining})


def resolve_contradictions(
    handoff: StructuredHandoff,
    pairs: list[tuple[HandoffFieldName, HandoffFieldName]],
) -> StructuredHandoff:
    """Fold :func:`resolve_contradiction` over ``pairs``.

    Each pair must exist at the moment it is resolved, else
    ContradictionNotFoundError. Fields are never modified.
    """
    updated = handoff
    for field_a, field_b in pairs:
        updated = resolve_contradiction(updated, field_a, field_b)
    return updated