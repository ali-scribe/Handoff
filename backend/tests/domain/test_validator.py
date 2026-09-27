"""Core behavior tests for the deterministic readiness validator.

Standard Pytest only (no Hypothesis / property-based testing), run fully offline
with no AI, network, or external services (Req 7.1). Every handoff is constructed
directly in test code (Req 7.2).

Covers Task 6.1: issue-detection rules, readiness reduction, false-positive
guards, idempotence, declared contradictions, issue-structure invariants, and the
empty-issue -> READY case. The seven worked-example scenarios are Task 6.2 and are
intentionally NOT included here.
"""

import pytest

from app.domain import (
    FieldCondition,
    HandoffField,
    HandoffFieldName,
    Issue,
    IssueSeverity,
    IssueType,
    ReadinessState,
    StructuredHandoff,
    ValidationResult,
    validate_handoff,
)
from app.domain.validator import _derive_readiness

# Short aliases to keep parametrize tables readable.
FN = HandoffFieldName
FC = FieldCondition
IT = IssueType
SEV = IssueSeverity


# ---------------------------------------------------------------------------
# DRY handoff builder
# ---------------------------------------------------------------------------
#
# Baseline: a fully-clear, READY handoff. Every required/optional field is
# PRESENT with a simple value; constraints and dependencies are NOT_APPLICABLE.
# Tests override individual fields to trigger exactly the rule under test.

_BASELINE: dict[str, HandoffField] = {
    "objective": HandoffField(value="Ship the Q3 report", condition=FC.PRESENT),
    "owner": HandoffField(value="Alex", condition=FC.PRESENT),
    "inputs": HandoffField(value=["data.csv"], condition=FC.PRESENT),
    "expected_output": HandoffField(value="A PDF report", condition=FC.PRESENT),
    "deadline": HandoffField(value="2025-01-31", condition=FC.PRESENT),
    "acceptance_criteria": HandoffField(value=["passes review"], condition=FC.PRESENT),
    "context": HandoffField(value="Quarterly numbers", condition=FC.PRESENT),
    "constraints": HandoffField(value=None, condition=FC.NOT_APPLICABLE),
    "dependencies": HandoffField(value=None, condition=FC.NOT_APPLICABLE),
}


def make_handoff(
    *,
    contradictions: list[tuple[HandoffFieldName, HandoffFieldName]] | None = None,
    **overrides: HandoffField | tuple[object, FieldCondition],
) -> StructuredHandoff:
    """Build a StructuredHandoff from the fully-clear baseline with overrides.

    Each override may be a ready-made ``HandoffField`` or a ``(value, condition)``
    tuple, which is wrapped for convenience. ``contradictions`` sets the declared
    contradiction pairs. Anything not overridden keeps its clear baseline value,
    so a test only has to state the field(s) it cares about.
    """
    fields = dict(_BASELINE)
    for name, override in overrides.items():
        if isinstance(override, HandoffField):
            fields[name] = override
        else:
            value, condition = override
            fields[name] = HandoffField(value=value, condition=condition)
    return StructuredHandoff(
        **fields,
        contradictions=contradictions or [],
    )


def _issue(severity: IssueSeverity) -> Issue:
    """Build a valid Issue with the given severity for readiness-reduction tests.

    The issue_type/field are arbitrary-but-valid; only ``severity`` matters here.
    """
    return Issue(
        issue_type=IssueType.MISSING_OBJECTIVE,
        severity=severity,
        field=HandoffFieldName.OBJECTIVE,
        explanation="synthetic issue for readiness reduction",
    )


# ---------------------------------------------------------------------------
# 1) Issue-detection rules — one parametrized test over the ten design rows
#    (Req 4.1-4.10, 5.2-5.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "contradictions", "issue_type", "field", "severity", "secondary"),
    [
        # Rule 1: objective MISSING -> missing_objective/CRITICAL (Req 4.1, 5.2)
        (
            {"objective": (None, FC.MISSING)},
            None,
            IT.MISSING_OBJECTIVE,
            FN.OBJECTIVE,
            SEV.CRITICAL,
            None,
        ),
        # Rule 2: objective AMBIGUOUS -> vague_objective/IMPORTANT (Req 4.2, 5.3)
        (
            {"objective": ("make it better", FC.AMBIGUOUS)},
            None,
            IT.VAGUE_OBJECTIVE,
            FN.OBJECTIVE,
            SEV.IMPORTANT,
            None,
        ),
        # Rule 3: inputs MISSING (required) -> missing_required_input/CRITICAL (Req 4.3, 5.2)
        (
            {"inputs": (None, FC.MISSING)},
            None,
            IT.MISSING_REQUIRED_INPUT,
            FN.INPUTS,
            SEV.CRITICAL,
            None,
        ),
        # Rule 4: expected_output MISSING -> missing_expected_output/CRITICAL (Req 4.4, 5.2)
        (
            {"expected_output": (None, FC.MISSING)},
            None,
            IT.MISSING_EXPECTED_OUTPUT,
            FN.EXPECTED_OUTPUT,
            SEV.CRITICAL,
            None,
        ),
        # Rule 5: deadline AMBIGUOUS -> vague_deadline/IMPORTANT (Req 4.5, 5.3)
        (
            {"deadline": ("soon", FC.AMBIGUOUS)},
            None,
            IT.VAGUE_DEADLINE,
            FN.DEADLINE,
            SEV.IMPORTANT,
            None,
        ),
        # Rule 6: acceptance_criteria MISSING (required) ->
        #         missing_acceptance_criteria/IMPORTANT (Req 4.6, 5.3)
        (
            {"acceptance_criteria": (None, FC.MISSING)},
            None,
            IT.MISSING_ACCEPTANCE_CRITERIA,
            FN.ACCEPTANCE_CRITERIA,
            SEV.IMPORTANT,
            None,
        ),
        # Rule 7: dependencies MISSING (required) -> unresolved_dependency/IMPORTANT (Req 4.7, 5.3)
        (
            {"dependencies": (None, FC.MISSING)},
            None,
            IT.UNRESOLVED_DEPENDENCY,
            FN.DEPENDENCIES,
            SEV.IMPORTANT,
            None,
        ),
        # Rule 9: owner MISSING (required) -> ambiguous_ownership/IMPORTANT (Req 4.9, 5.3)
        (
            {"owner": (None, FC.MISSING)},
            None,
            IT.AMBIGUOUS_OWNERSHIP,
            FN.OWNER,
            SEV.IMPORTANT,
            None,
        ),
        # Rule 10: expected_output AMBIGUOUS -> vague_action_language/MINOR (Req 4.10, 5.4)
        (
            {"expected_output": ("something good", FC.AMBIGUOUS)},
            None,
            IT.VAGUE_ACTION_LANGUAGE,
            FN.EXPECTED_OUTPUT,
            SEV.MINOR,
            None,
        ),
        # Rule 8: declared contradiction (deadline, dependencies) ->
        #         contradictory_information/CRITICAL, field=deadline,
        #         secondary_field=dependencies (Req 4.8, 5.2)
        (
            {"dependencies": (["vendor delivers next week"], FC.PRESENT)},
            [(FN.DEADLINE, FN.DEPENDENCIES)],
            IT.CONTRADICTORY_INFORMATION,
            FN.DEADLINE,
            SEV.CRITICAL,
            FN.DEPENDENCIES,
        ),
    ],
)
def test_issue_detection_rule_fires_exactly_once(
    overrides, contradictions, issue_type, field, severity, secondary
) -> None:
    """Each triggering (field, condition) yields exactly one issue of the mapped type.

    Filters the produced issues by ``issue_type`` and asserts there is exactly one,
    with the expected associated field and severity (plus secondary_field for the
    contradiction row). Other rules may co-fire (e.g. rule 2 + rule 10 on an
    ambiguous objective), which is why we filter by type rather than count all.
    """
    result = validate_handoff(make_handoff(contradictions=contradictions, **overrides))
    matching = [i for i in result.issues if i.issue_type is issue_type]
    assert len(matching) == 1
    issue = matching[0]
    assert issue.field is field
    assert issue.severity is severity
    assert issue.secondary_field is secondary


# ---------------------------------------------------------------------------
# 2) Readiness reduction — one parametrized test over hand-built issue lists
#    (Req 3.3-3.6, 5.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ([], ReadinessState.READY),  # empty -> READY (Req 3.6)
        ([SEV.MINOR], ReadinessState.READY),  # only MINOR -> READY (Req 3.5, 5.5)
        ([SEV.MINOR, SEV.MINOR], ReadinessState.READY),  # many MINOR -> READY
        ([SEV.IMPORTANT], ReadinessState.NEEDS_CLARIFICATION),  # IMPORTANT (Req 3.4)
        (
            [SEV.IMPORTANT, SEV.MINOR],
            ReadinessState.NEEDS_CLARIFICATION,
        ),  # IMPORTANT dominates MINOR (Req 3.4, 5.5)
        ([SEV.CRITICAL], ReadinessState.NOT_READY),  # CRITICAL (Req 3.3)
        (
            [SEV.CRITICAL, SEV.IMPORTANT, SEV.MINOR],
            ReadinessState.NOT_READY,
        ),  # CRITICAL dominates all (Req 3.3)
    ],
)
def test_readiness_reduction(severities, expected) -> None:
    """_derive_readiness reduces an issue list to the exact readiness verdict."""
    issues = [_issue(sev) for sev in severities]
    assert _derive_readiness(issues) is expected


# ---------------------------------------------------------------------------
# 3) False-positive guards (Req 4.11, 4.12, 7.10)
# ---------------------------------------------------------------------------

# Missing-information issue types that a NOT_APPLICABLE field must never produce.
_MISSING_INFO_TYPES = {
    IT.MISSING_REQUIRED_INPUT,
    IT.MISSING_ACCEPTANCE_CRITERIA,
    IT.UNRESOLVED_DEPENDENCY,
    IT.AMBIGUOUS_OWNERSHIP,
}


@pytest.mark.parametrize(
    "field_name",
    ["inputs", "owner", "acceptance_criteria", "dependencies"],
)
def test_not_applicable_field_yields_no_missing_information_issue(field_name) -> None:
    """A NOT_APPLICABLE required-unless-NA field produces no missing-information issue.

    Guards against false positives: even though the field would otherwise be
    required, marking it NOT_APPLICABLE short-circuits any missing_* /
    unresolved_dependency / ambiguous_ownership issue for it (Req 4.11, 7.10).
    """
    result = validate_handoff(make_handoff(**{field_name: (None, FC.NOT_APPLICABLE)}))
    target = FN(field_name)
    offending = [
        i
        for i in result.issues
        if i.field is target and i.issue_type in _MISSING_INFO_TYPES
    ]
    assert offending == []


def test_non_required_missing_field_yields_no_critical_issue() -> None:
    """A non-required MISSING field never yields a CRITICAL issue for being absent (Req 4.12).

    ``inputs`` marked NOT_APPLICABLE is no longer required, so its absence produces
    no CRITICAL. ``deadline`` set to MISSING is an optional field with no missing
    rule, so it produces no issue at all. The overall result stays clear of any
    CRITICAL issue.
    """
    result = validate_handoff(
        make_handoff(
            inputs=(None, FC.NOT_APPLICABLE),
            deadline=(None, FC.MISSING),
        )
    )
    # No CRITICAL issue anywhere (nothing essential is actually absent).
    assert all(i.severity is not SEV.CRITICAL for i in result.issues)
    # inputs (non-required now) triggers no CRITICAL.
    assert not any(
        i.field is FN.INPUTS and i.severity is SEV.CRITICAL for i in result.issues
    )
    # deadline MISSING is optional -> no issue references deadline at all.
    assert not any(i.field is FN.DEADLINE for i in result.issues)


# ---------------------------------------------------------------------------
# 4) Idempotence (Req 3.7, 4.13)
# ---------------------------------------------------------------------------


def test_validation_is_idempotent() -> None:
    """Validating the same handoff twice yields two equal ValidationResults.

    Uses a mixed handoff (AMBIGUOUS deadline + MISSING acceptance_criteria) so the
    result carries issues; equal results confirm deterministic, side-effect-free
    validation (Req 3.7, 4.13).
    """
    handoff = make_handoff(
        deadline=("soon", FC.AMBIGUOUS),
        acceptance_criteria=(None, FC.MISSING),
    )
    first = validate_handoff(handoff)
    second = validate_handoff(handoff)
    assert first == second
    assert first.readiness_state == second.readiness_state
    assert isinstance(first, ValidationResult)


# ---------------------------------------------------------------------------
# 5) Declared contradiction (Req 4.8, 5.2)
# ---------------------------------------------------------------------------


def test_declared_contradiction_produces_single_critical_issue() -> None:
    """A declared (objective, deadline) contradiction yields one CRITICAL issue.

    The issue is contradictory_information with field=objective and
    secondary_field=deadline and a non-empty explanation; readiness is NOT_READY
    (Req 4.8, 5.2).
    """
    result = validate_handoff(
        make_handoff(contradictions=[(FN.OBJECTIVE, FN.DEADLINE)])
    )
    contradictions = [
        i for i in result.issues if i.issue_type is IT.CONTRADICTORY_INFORMATION
    ]
    assert len(contradictions) == 1
    issue = contradictions[0]
    assert issue.severity is SEV.CRITICAL
    assert issue.field is FN.OBJECTIVE
    assert issue.secondary_field is FN.DEADLINE
    assert issue.explanation.strip() != ""
    assert result.readiness_state is ReadinessState.NOT_READY


# ---------------------------------------------------------------------------
# 6) Issue-structure invariant (Req 5.1, 6.3)
# ---------------------------------------------------------------------------


def test_every_issue_has_valid_severity_field_and_explanation() -> None:
    """Every produced issue carries a valid severity, a HandoffFieldName, and text.

    Uses a handoff producing several issues (AMBIGUOUS objective -> vague_objective
    + vague_action_language, AMBIGUOUS deadline -> vague_deadline, MISSING owner ->
    ambiguous_ownership) so multiple issues are checked (Req 5.1, 6.3).
    """
    result = validate_handoff(
        make_handoff(
            objective=("make it better", FC.AMBIGUOUS),
            deadline=("soon", FC.AMBIGUOUS),
            owner=(None, FC.MISSING),
        )
    )
    assert len(result.issues) >= 3
    for issue in result.issues:
        assert issue.severity in set(IssueSeverity)
        assert isinstance(issue.field, HandoffFieldName)
        assert isinstance(issue.explanation, str)
        assert issue.explanation.strip() != ""


# ---------------------------------------------------------------------------
# 7) Empty issue list -> READY (Req 3.6, 6.4)
# ---------------------------------------------------------------------------


def test_fully_clear_handoff_is_ready_with_no_issues() -> None:
    """A fully-clear handoff yields an empty issue list and READY (Req 3.6, 6.4)."""
    result = validate_handoff(make_handoff())
    assert result.issues == []
    assert result.readiness_state is ReadinessState.READY


# ===========================================================================
# Worked-example scenarios (Req 7.3-7.10)
# ===========================================================================
#
# One test per worked example from design.md "Worked Examples" (Examples 1-7).
# Field notation follows the design: P=PRESENT, M=MISSING, A=AMBIGUOUS,
# NA=NOT_APPLICABLE. Order per design: objective, owner, inputs,
# expected_output, deadline, acceptance_criteria, context, constraints,
# dependencies. Each test reuses make_handoff (baseline = the fully-clear,
# Example-1 handoff) and overrides only the fields the example changes.


def test_example_1_clearly_executable_is_ready() -> None:
    """Example 1 - clearly executable handoff -> READY (Req 7.3).

    objective P, owner P, inputs P, expected_output P, deadline P,
    acceptance_criteria P, context P, constraints NA, dependencies NA.
    This is exactly the fully-clear baseline, so make_handoff() with no overrides
    reproduces it. No issues fire; readiness is READY (Req 3.6, 4.11).
    """
    result = validate_handoff(make_handoff())
    assert result.issues == []
    assert result.readiness_state is ReadinessState.READY


def test_example_2_missing_critical_info_is_not_ready() -> None:
    """Example 2 - missing critical info -> NOT_READY (Req 7.4).

    objective M and expected_output M (others P; constraints/dependencies NA).
    Both are always-required, so each yields a CRITICAL issue: missing_objective
    (objective) and missing_expected_output (expected_output). Readiness is
    NOT_READY (Req 3.3).
    """
    result = validate_handoff(
        make_handoff(
            objective=(None, FC.MISSING),
            expected_output=(None, FC.MISSING),
        )
    )
    assert result.readiness_state is ReadinessState.NOT_READY

    missing_objective = [
        i for i in result.issues if i.issue_type is IT.MISSING_OBJECTIVE
    ]
    assert len(missing_objective) == 1
    assert missing_objective[0].field is FN.OBJECTIVE
    assert missing_objective[0].severity is SEV.CRITICAL

    missing_output = [
        i for i in result.issues if i.issue_type is IT.MISSING_EXPECTED_OUTPUT
    ]
    assert len(missing_output) == 1
    assert missing_output[0].field is FN.EXPECTED_OUTPUT
    assert missing_output[0].severity is SEV.CRITICAL


def test_example_3_mostly_complete_needs_clarification() -> None:
    """Example 3 - mostly complete, a few questions -> NEEDS_CLARIFICATION (Req 7.5).

    deadline A and acceptance_criteria M (required) (others P;
    constraints/dependencies NA). Fires vague_deadline (IMPORTANT) and
    missing_acceptance_criteria (IMPORTANT) with no CRITICAL, so readiness is
    NEEDS_CLARIFICATION (Req 3.4).
    """
    result = validate_handoff(
        make_handoff(
            deadline=("soon", FC.AMBIGUOUS),
            acceptance_criteria=(None, FC.MISSING),
        )
    )
    assert result.readiness_state is ReadinessState.NEEDS_CLARIFICATION

    vague_deadline = [i for i in result.issues if i.issue_type is IT.VAGUE_DEADLINE]
    assert len(vague_deadline) == 1
    assert vague_deadline[0].field is FN.DEADLINE
    assert vague_deadline[0].severity is SEV.IMPORTANT

    missing_ac = [
        i for i in result.issues if i.issue_type is IT.MISSING_ACCEPTANCE_CRITERIA
    ]
    assert len(missing_ac) == 1
    assert missing_ac[0].field is FN.ACCEPTANCE_CRITERIA
    assert missing_ac[0].severity is SEV.IMPORTANT

    # No CRITICAL issues present.
    assert all(i.severity is not SEV.CRITICAL for i in result.issues)


def test_example_4_vague_software_request_needs_clarification() -> None:
    """Example 4 - vague software-development request -> NEEDS_CLARIFICATION (Req 7.6).

    objective A, expected_output A, deadline NA, acceptance_criteria M (required)
    (others P; constraints/dependencies NA). Demonstrates rule 2 + rule 10
    co-firing on objective: vague_objective (IMPORTANT, objective),
    vague_action_language (MINOR) on both objective and expected_output, plus
    missing_acceptance_criteria (IMPORTANT). No CRITICAL, so NEEDS_CLARIFICATION
    (Req 3.4).
    """
    result = validate_handoff(
        make_handoff(
            objective=("make the app better", FC.AMBIGUOUS),
            expected_output=("something good", FC.AMBIGUOUS),
            deadline=(None, FC.NOT_APPLICABLE),
            acceptance_criteria=(None, FC.MISSING),
        )
    )
    assert result.readiness_state is ReadinessState.NEEDS_CLARIFICATION

    vague_objective = [
        i for i in result.issues if i.issue_type is IT.VAGUE_OBJECTIVE
    ]
    assert len(vague_objective) == 1
    assert vague_objective[0].field is FN.OBJECTIVE
    assert vague_objective[0].severity is SEV.IMPORTANT

    missing_ac = [
        i for i in result.issues if i.issue_type is IT.MISSING_ACCEPTANCE_CRITERIA
    ]
    assert len(missing_ac) == 1
    assert missing_ac[0].field is FN.ACCEPTANCE_CRITERIA
    assert missing_ac[0].severity is SEV.IMPORTANT

    # Rule 2 + rule 10 co-fire on objective; rule 10 also fires on expected_output.
    # Both vague_action_language issues are MINOR and cover exactly those two fields.
    vague_action = [
        i for i in result.issues if i.issue_type is IT.VAGUE_ACTION_LANGUAGE
    ]
    assert len(vague_action) == 2
    assert all(i.severity is SEV.MINOR for i in vague_action)
    assert {i.field for i in vague_action} == {FN.OBJECTIVE, FN.EXPECTED_OUTPUT}

    # No CRITICAL issues present.
    assert all(i.severity is not SEV.CRITICAL for i in result.issues)


def test_example_5_university_assignment_is_ready() -> None:
    """Example 5 - university assignment/task handoff -> READY (Req 7.7, 7.10).

    owner NA and dependencies NA (objective P, inputs P, expected_output P,
    deadline P, acceptance_criteria P, context P, constraints P). No issues fire;
    readiness is READY.

    NOT_APPLICABLE false-positive guard (Req 7.10): owner NA and dependencies NA
    must produce NO issue for those fields even though they are otherwise
    required-unless-NA.
    """
    result = validate_handoff(
        make_handoff(
            owner=(None, FC.NOT_APPLICABLE),
            constraints=(["budget under $50"], FC.PRESENT),
            dependencies=(None, FC.NOT_APPLICABLE),
        )
    )
    assert result.issues == []
    assert result.readiness_state is ReadinessState.READY

    # False-positive guard: no issue is associated with owner or dependencies.
    assert not any(i.field is FN.OWNER for i in result.issues)
    assert not any(i.field is FN.DEPENDENCIES for i in result.issues)


def test_example_6_small_business_operational_task_is_ready() -> None:
    """Example 6 - small-business operational task -> READY (Req 7.8, 7.10).

    owner NA, acceptance_criteria NA, dependencies NA (objective P, inputs P,
    expected_output P, deadline P, context P, constraints P). No issues fire;
    readiness is READY.

    NOT_APPLICABLE false-positive guard (Req 7.10): owner NA, acceptance_criteria
    NA, and dependencies NA must produce NO issue for those fields.
    """
    result = validate_handoff(
        make_handoff(
            owner=(None, FC.NOT_APPLICABLE),
            acceptance_criteria=(None, FC.NOT_APPLICABLE),
            constraints=(["open by 8am"], FC.PRESENT),
            dependencies=(None, FC.NOT_APPLICABLE),
        )
    )
    assert result.issues == []
    assert result.readiness_state is ReadinessState.READY

    # False-positive guard: no issue is associated with owner, acceptance_criteria,
    # or dependencies.
    assert not any(i.field is FN.OWNER for i in result.issues)
    assert not any(i.field is FN.ACCEPTANCE_CRITERIA for i in result.issues)
    assert not any(i.field is FN.DEPENDENCIES for i in result.issues)


def test_example_7_contradictory_information_is_not_ready() -> None:
    """Example 7 - contradictory information -> NOT_READY (Req 7.9).

    All nine fields P except constraints NA (objective P, owner P, inputs P,
    expected_output P, deadline P, acceptance_criteria P, context P,
    constraints NA, dependencies P), with a declared contradiction between
    deadline and dependencies. Exactly one contradictory_information issue
    (CRITICAL, field=deadline, secondary_field=dependencies) fires, so readiness
    is NOT_READY (Req 3.3, 4.8).
    """
    result = validate_handoff(
        make_handoff(
            dependencies=(["after vendor delivers next week"], FC.PRESENT),
            contradictions=[(FN.DEADLINE, FN.DEPENDENCIES)],
        )
    )
    assert result.readiness_state is ReadinessState.NOT_READY

    contradictions = [
        i for i in result.issues if i.issue_type is IT.CONTRADICTORY_INFORMATION
    ]
    assert len(contradictions) == 1
    issue = contradictions[0]
    assert issue.severity is SEV.CRITICAL
    assert issue.field is FN.DEADLINE
    assert issue.secondary_field is FN.DEPENDENCIES
