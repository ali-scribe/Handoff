# Handoff

**Handoff checks whether a work request contains enough information for someone else to actually execute it.**

When people hand off work (a task, a ticket, a project brief) they often leave out the details the other person needs: what "done" looks like, who owns it, what inputs are required, when it is due. Handoff takes a plain-language request, extracts its structure, and tells you whether it is ready to hand off, what is missing, and how to close the gaps.

This is a university project / demo. It is built around a clear principle: **the AI extracts information, but a deterministic validator (not the AI) decides readiness.**

## The problem it solves

A request like *"Please fix the login bug before Friday and send me the updated code"* sounds actionable but may be missing an owner, acceptance criteria, or concrete inputs. Handoff makes those gaps explicit before the work is handed off, instead of after it goes wrong.

## Core workflow

```
request text
   -> AI extraction             (Gemini turns free text into nine structured fields)
   -> deterministic validation  (pure rules decide readiness + issues)
   -> clarification             (generated questions; you answer; re-validate)
   -> execution-ready handoff   (formatted, copyable text)
```

1. **Request to AI extraction.** The raw text is sent to Google Gemini, which extracts nine fields (objective, owner, inputs, expected output, deadline, acceptance criteria, context, constraints, dependencies). Each field gets a condition: `present`, `missing`, `ambiguous`, or `not_applicable`. The AI only extracts; it never decides readiness and never invents values.
2. **Deterministic validation.** A pure, testable validator applies fixed rules to the structured fields and produces a readiness verdict (`ready`, `needs_clarification`, or `not_ready`) plus a list of issues, each with a severity (`critical`, `important`, or `minor`). This logic is fully deterministic and independent of the AI.
3. **Clarification.** When information is missing or ambiguous, Handoff generates targeted clarification questions. You answer them, and the handoff is re-validated. Declared contradictions can be explicitly resolved.
4. **Execution-ready handoff.** Once ready, the handoff is formatted into a clean, copyable text block.

## Key features

- Nine-field structured extraction with an explicit per-field condition.
- Deterministic readiness validation as the single source of truth (the AI never decides readiness).
- Clarification questions generated from detected issues, with answer application and re-validation.
- Explicit contradiction resolution.
- Formatting into an execution-ready handoff.
- Optional missing fields (e.g. context, constraints) do not block a ready handoff.
- Structured, secret-safe API error handling (no keys or raw provider responses in errors).
- Light/dark theme with a warm, editorial visual design.
- Built-in example requests to try the full flow immediately.
- An offline evaluation harness for measuring real-world quality against a labeled dataset.

## Tech stack

**Frontend** - React 19, TypeScript, Vite, Vitest + Testing Library. No UI framework or state library; a single global stylesheet.

**Backend** - Python, FastAPI, Pydantic v2, httpx, pytest. Google Gemini via its REST API for extraction. `python-dotenv` for local configuration.

## Project structure

```
Handoff/
|-- backend/
|   |-- app/
|   |   |-- api/            # FastAPI routes, request/response DTOs, error handling
|   |   |-- application/    # analysis + clarification orchestration (no business rules)
|   |   |-- domain/         # StructuredHandoff model + deterministic validator (readiness authority)
|   |   |-- extraction/     # Gemini provider, extraction service, config
|   |   |-- main.py         # FastAPI entrypoint (loads backend/.env)
|   |-- evaluation/         # offline evaluation harness + seed dataset
|   |-- tests/              # backend test suite
|   |-- requirements.txt
|   |-- .env.example
|-- frontend/
    |-- src/
        |-- api/            # typed API client (only place that calls fetch)
        |-- components/     # input, results, clarification, execution-ready, etc.
        |-- data/           # built-in demo examples
        |-- types/          # TypeScript mirrors of the API DTOs
```

The frontend never recomputes readiness; it renders exactly what the backend returns.

## API endpoints

All routes are served under the /api prefix:

- GET  /api/health - liveness check.
- POST /api/handoff/analyze - extract + validate a raw request.
- POST /api/handoff/clarify - generate clarification questions for a handoff.
- POST /api/handoff/apply-answers - apply answers, resolve contradictions, re-validate.
- POST /api/handoff/format - render a handoff to execution-ready text.

## Local setup

Prerequisites: Python 3.12+ and Node.js 18+. You will need a Google Gemini API key.

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

Configure Gemini by copying the example env file and filling in your key:

```bash
cp .env.example .env      # from the backend/ directory
```

Then edit backend/.env:

```
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-flash-lite-latest
GEMINI_TIMEOUT_SECONDS=30.0
```

GEMINI_MODEL and GEMINI_TIMEOUT_SECONDS are optional (defaults: gemini-2.0-flash, 30.0). The .env file is git-ignored; never commit a real key.

Run the backend API:

```bash
python -m uvicorn app.main:app --port 8000
```

The app loads backend/.env automatically on startup.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (default http://localhost:5173). The Vite dev proxy forwards /api to the backend at http://localhost:8000, so keep the backend process active at the same time.

To build for production:

```bash
npm run build
```

## Running tests

Tests are deterministic and do not call Gemini.

Backend (from backend/):

```bash
python -m pytest
```

Frontend (from frontend/):

```bash
npm test
```

## Evaluation

Software tests confirm the code works; they do not tell us whether Handoff makes good judgments on realistic requests. The backend/evaluation/ harness runs a small, manually labeled dataset through the real pipeline (real Gemini extraction + deterministic validation) and reports quality metrics.

Run it explicitly (needs a valid GEMINI_API_KEY), from backend/:

```bash
python -m evaluation.run_evaluation
python -m evaluation.run_evaluation --write-results
python -m evaluation.run_evaluation --diagnostic
```

Metrics include readiness accuracy, critical-issue detection, false-positive rate, false-negative count, and a per-category breakdown. See backend/evaluation/README.md for details.

### Evaluation results and limitations

The current dataset is an 8-case seed whose only purpose is to validate that the evaluation infrastructure works; it is not evidence that Handoff is accurate in general. Because AI extraction is probabilistic, metrics vary between runs, and transient Gemini timeouts are recorded as infrastructure errors (excluded from accuracy), not model failures. Meaningful quality measurement would require a larger, carefully labeled dataset (target: ~50-100 human-reviewed cases). Expected labels are always assigned by human judgment, never generated by running Handoff.

## Built-in examples

The input screen offers three example requests you can load into the textarea with one click (they do not auto-submit and stay editable):

- Incomplete request - missing key details; demonstrates what Handoff asks for.
- Ambiguous request - has structure but vague language to clarify.
- Ready request - concrete and complete; demonstrates the successful path.

Each runs through the exact same real pipeline as typed input.

## Current limitations / out of scope

- Requires a Google Gemini API key; there is no offline extraction mode.
- Extraction is probabilistic, so results for the same request can vary between runs.
- No persistence: handoffs, history, and results are not stored in a database.
- No user accounts, authentication, or multi-user features.
- Contradiction detection reports only contradictions the extractor declares; it does not perform its own semantic conflict analysis.
- The evaluation dataset is a small seed, not a benchmark.
- No deployment/hosting configuration is included; setup is for local development.
