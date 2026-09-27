# Handoff Evaluation

## Why evaluation exists

The automated test suite proves the **code works** â€” that functions, endpoints,
and the state machine behave as written. It does **not** tell us whether Handoff
makes *good judgments* on realistic work requests: does it correctly recognize
when a request is executable, and does it flag genuinely missing information
without blocking requests that are actually ready?

This evaluation infrastructure answers those product-quality questions by
running a manually labeled dataset of realistic requests through the **real**
Handoff pipeline and comparing the results to human-reviewed ground truth.

## Software tests vs. product evaluation

| Software tests | Product evaluation |
| --- | --- |
| Deterministic, mock the AI | Uses the real AI extraction |
| "Does the code do what we wrote?" | "Does the product make good decisions?" |
| Must always pass | Reports a quality score that can move |
| No external calls | Calls Gemini for each case |

## Dataset structure

`handoff_cases.json`:

```json
{
  "version": 1,
  "cases": [
    {
      "id": "eval-001",
      "category": "software",
      "request": "...",
      "expected_readiness": "not_ready",
      "expected_critical_fields": ["objective", "expected_output"],
      "notes": "why a human labeled it this way"
    }
  ]
}
```

### Meaning of each expected field

- **id** â€” unique, stable case identifier.
- **category** â€” domain (software, university, freelance, small_business,
  content_design, everyday, ...). Used for the per-category breakdown.
- **request** â€” the raw request text, exactly as a user would type it.
- **expected_readiness** â€” the human-reviewed correct readiness. Must be one of
  the backend `ReadinessState` values: `ready`, `needs_clarification`,
  `not_ready`.
- **expected_critical_fields** â€” the fields a human reviewer considers genuine
  critical blockers for this request. Must be valid `HandoffFieldName` values
  (`objective`, `owner`, `inputs`, `expected_output`, `deadline`,
  `acceptance_criteria`, `context`, `constraints`, `dependencies`). Use an empty
  array when there is no critical blocker. **Not every case needs one.**
- **notes** *(optional)* â€” the human reasoning behind the labels.

## How to run

The evaluation is **never** run automatically. Run it explicitly from the
`backend/` directory, with the same environment/`.env` the app uses (it needs a
valid `GEMINI_API_KEY`):

```bash
cd backend
python -m evaluation.run_evaluation                 # print summary only
python -m evaluation.run_evaluation --write-results  # also write evaluation-results.json
python -m evaluation.run_evaluation --diagnostic     # also write evaluation-diagnostics.json
```

It reuses the app's own configuration and provider â€” there is no separate Gemini
setup. `evaluation-results.json` is only written when you pass
`--write-results`.

## Diagnostic mode

`--diagnostic` runs the same real `get_analysis_service()` pipeline and, for
every successfully evaluated case, serializes the full real domain objects for
human investigation:

- the case id / category / request,
- expected readiness and expected critical fields,
- the complete `StructuredHandoff` extraction (every field name, its condition,
  and its value),
- the complete `ValidationResult` (readiness plus every issue: issue type,
  field, secondary field when present, severity, and message),
- any contradictions already present on the domain model,
- whether predicted readiness matched expected readiness.

It writes `evaluation-diagnostics.json` (git-ignored) alongside the normal
output. Normal execution and `evaluation-results.json` are unchanged.

For provider errors (e.g. timeouts) the case is recorded with its error and
no fabricated extraction/validation; other cases still run. The diagnostic file
never contains API keys, environment variables, authorization headers, or raw
provider responses - only the serialized domain objects.

Diagnostic output is for human investigation only. It is NOT automatically
generated ground truth: do not copy predicted readiness or fields into the
dataset expected labels. Ground truth must always be decided by human judgment
(see "Why expected labels must be manually reviewed").
## What each metric means

- **Readiness accuracy** â€” fraction of evaluated cases where predicted readiness
  equals the expected readiness.
- **Critical issue detection** â€” of the expected critical fields across all
  cases, how many the pipeline flagged with a `CRITICAL` issue (severity comes
  from the existing `IssueSeverity` model; nothing here redefines "critical").
- **False positive rate** â€” of cases expected to be `ready`, how many the
  pipeline predicted as non-`ready`. `null` when there are no ready cases.
- **False negative count** â€” cases expected to be non-`ready` that the pipeline
  predicted as `ready` (a useful safety signal).
- **Category breakdown** â€” readiness accuracy grouped by category.

Errored cases (API/config/runtime failures) are reported separately and are
**excluded from every accuracy denominator** â€” an infrastructure error is not a
model failure.

## How to add new cases

1. Write a realistic `request`.
2. **Before running Handoff**, reason as a human: could someone actually execute
   this? What is genuinely missing? Decide `expected_readiness` and
   `expected_critical_fields` from that reasoning alone.
3. Give the case a new unique `id` and a `category`.
4. Add it to the `cases` array and run the evaluation tests
   (`pytest tests/evaluation`) to confirm the dataset is still structurally
   valid.

## Why expected labels must be manually reviewed

The `expected_*` values are **ground truth** and must be independent of the
system being measured. If you generated them by running Handoff first, the
evaluation would only confirm that Handoff agrees with itself. Label each case
by human judgment about what a real assignee would need.

## Uses the real AI pipeline

The runner calls the production `AnalysisService` (built by the app's own
`get_analysis_service()` factory): real Gemini extraction â†’ structured handoff â†’
deterministic validation â†’ readiness. No extraction is faked or mocked in the
runner, and no readiness/validation logic is duplicated here.

## Results vary between runs

Because AI extraction is probabilistic, the same request can extract slightly
differently across runs, so metrics may move between executions. This is
expected. Cases that depend on the model *declaring* a contradiction are
especially variable.

## Important limitation

This seed dataset contains only **8 cases**. That is enough to validate that the
evaluation *infrastructure* works â€” it is **not** evidence that Handoff is
accurate in general. Real quality measurement requires a larger, carefully
labeled dataset (target: ~50â€“100 manually reviewed cases). Do not draw
conclusions about Handoff's general accuracy from 8 cases.
