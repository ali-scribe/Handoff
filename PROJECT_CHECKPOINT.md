# Handoff — Project Checkpoint

Handoff is a web app that checks whether a work request contains enough information for
someone else to actually execute it. It turns messy natural-language requests into a
structured representation, deterministically decides readiness, asks minimal clarification
questions, applies answers, and produces an execution-ready handoff.

Guiding principle throughout: **AI extracts information; deterministic code decides
readiness.** An LLM never decides READY / NEEDS_CLARIFICATION / NOT_READY.

_Last updated: this checkpoint reflects the state after the Gemini model-availability
diagnosis (see Known Issues)._

---

## 1. Current implementation state

End-to-end MVP is implemented and verified: backend pipeline + REST API + React frontend.

- **Backend**: FastAPI + Pydantic v2 (Python 3.14), served by uvicorn. Fully implemented:
  domain model, deterministic validator, AI extraction, clarification engine, and the HTTP API.
- **Frontend**: React 19 + TypeScript + Vite 6 MVP implementing the full loop
  (input → analyze → results → clarify/apply → format → copy → reset).
- **Live status**: `/api/health` returns 200; the AI-free endpoints (clarify, apply-answers,
  format) work end to end; `/api/handoff/analyze` reaches Gemini but currently fails on model
  availability (see Known Issues — a `.env` config change, not a code defect).

---

## 2. Completed specifications

All five specs are implemented and were verified at completion. Spec documents live under
`.kiro/specs/`.

1. **Core Handoff Analysis & Readiness Validation** — `StructuredHandoff` domain model and the
   pure, deterministic `validate_handoff()` (sole authority for readiness, severity, issues).
2. **AI Handoff Extraction** — messy text → `StructuredHandoff` via a provider abstraction
   (Gemini), typed extraction errors, env-based config. AI never decides readiness.
3. **Handoff Analysis API** — `POST /api/handoff/analyze` (extraction + deterministic validation),
   typed error → HTTP mapping, DTO/mapping layer.
4. **Handoff Clarification Engine** — deterministic question generation, answer application,
   explicit contradiction resolution, and a deterministic execution-ready formatter, exposed via
   `/clarify`, `/apply-answers`, `/format`.
5. **Handoff Frontend MVP** — typed API client, phase state machine, and the full UI loop.

Plus one **bug-fix spec** — _Analyze Error-Envelope Hardening_: a missing Gemini key now returns
the typed `{error:{code:"server_configuration_error",...}}` envelope (HTTP 500) instead of a raw
empty-body 500. Implemented via lazy config load in `GeminiProvider` (deferred to first `extract()`).

---

## 3. Architecture

### Pipeline
```
raw request text
  → ExtractionService (AI: GeminiProvider) → StructuredHandoff
  → validate_handoff() → ValidationResult (readiness + issues)
  → ClarificationEngine → Questions
  → Answer application (+ explicit contradiction resolution) → updated StructuredHandoff
  → validate_handoff() again
  → deterministic Formatter → execution-ready text
```

### Layering (strict separation; domain/application never import FastAPI)
```
API (app/api)            HTTP DTOs, routing, typed-error→HTTP mapping, DI
Application (app/application)  AnalysisService, clarification_flow orchestration
Domain (app/domain)      StructuredHandoff, validate_handoff, clarification, answers, formatter
Extraction (app/extraction)   ExtractionService, ExtractionProvider protocol, GeminiProvider, config, errors
```

### Backend module map (`backend/app/`)
- `domain/` — `handoff.py`, `validation.py`, `validator.py`, `clarification.py`, `answers.py`, `formatter.py`
- `extraction/` — `config.py`, `provider.py` (Protocol), `gemini_provider.py`, `schema.py`, `service.py`, `errors.py`
- `application/` — `analysis.py`, `clarification_flow.py`
- `api/` — `schemas.py`, `mapping.py`, `errors.py`, `dependencies.py`, `analyze.py`, `clarification.py`, `health.py`
- `main.py` — FastAPI app; loads `backend/.env` via `load_dotenv(..., override=False)`; includes routers under `/api`; registers error handlers.

### API surface
- `GET  /api/health` → `{"status":"ok"}`
- `POST /api/handoff/analyze` → `{handoff, validation}` (AI extraction; needs Gemini key)
- `POST /api/handoff/clarify` → `{questions}` (deterministic; no AI)
- `POST /api/handoff/apply-answers` → `{handoff, validation}` (answers + explicit `resolve_contradictions`; no AI)
- `POST /api/handoff/format` → `{text}` (deterministic; no AI)

All endpoints are stateless: the client sends the `StructuredHandoff` back on each call.
Errors use a uniform envelope: `{"error":{"code": <stable code>, "message": <safe message>}}`.

### Frontend (`frontend/src/`)
- `api/client.ts` — the only place `fetch()` is called; typed functions per endpoint + `getHealth`
- `api/errors.ts` — `ApiError` + safe `toUserMessage()` code mapping
- `types/handoff.ts` — TS mirrors of backend DTOs
- `hooks/useAsync.ts` — loading/error state helper
- `components/` — Header, InputView, ResultsView, ReadinessBadge, StructuredFields, IssueList,
  ClarificationView, ExecutionReadyView, Spinner, ErrorBanner
- `App.tsx` — phase state machine (input → results → ready); `index.css` — single global stylesheet
- Dev server proxies `/api` → `http://localhost:8000` (single origin, no CORS in dev).

### Key architectural guarantees (enforced by tests)
- Readiness/severity/requiredness computed only by `validate_handoff()` — never in the API,
  extraction, formatter, or frontend.
- No `fetch()` in React components (guard test); all network via the client.
- Contradiction resolution is explicit/user-authorized; ordinary answers never mutate contradictions.
- The Gemini API key is never logged, echoed, or sent to the frontend.

---

## 4. Test results

- **Backend**: `368 passed` (pytest), 2 pre-existing unrelated deprecation warnings
  (Starlette/httpx TestClient, anyio BlockingPortal), 0 failures.
- **Frontend**: `49 passed` across 10 test files (Vitest + Testing Library, jsdom); all offline
  with a mocked API client (no real network/AI).
- **Frontend production build**: `npm run build` (`tsc -b && vite build`) succeeds.
- All tests run offline; none require a real Gemini API call.

---

## 5. Environment configuration requirements

Backend configuration is read from environment variables (loaded from `backend/.env` at startup
via `python-dotenv`; real shell/server env vars take precedence).

Required / supported variables:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes (for `/analyze`) | — | Never commit; never exposed to the frontend |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Must be a model available to your key (see Known Issues) |
| `GEMINI_TIMEOUT_SECONDS` | No | `30.0` | Request timeout |

- `backend/.env` is git-ignored via the root `.gitignore` `.env` rule. `backend/.env.example`
  documents the variable names with placeholders only.
- The AI-free endpoints (`/clarify`, `/apply-answers`, `/format`, `/health`) do not require a key.
- Dependencies are pinned in `backend/requirements.txt` (fastapi, uvicorn[standard], pydantic,
  python-dotenv, pytest, httpx) and `frontend/package.json` (React 19, Vite 6, Vitest 4,
  Testing Library). No SDKs beyond these; Gemini is called via `httpx` REST.

---

## 6. Known issues

1. **Configured Gemini model is unavailable to new keys (config, not code).**
   A local `.env` set to `GEMINI_MODEL=gemini-2.5-flash-lite` causes `/api/handoff/analyze` to
   return HTTP 502 `provider_failure` (frontend: "The analysis service had a problem"). Root cause,
   confirmed directly from the Gemini API: `generateContent` on `gemini-2.5-flash-lite` returns
   **404 NOT_FOUND** — "no longer available to new users."
   **Fix (config only):** set `GEMINI_MODEL` in `backend/.env` to an available flash-lite model.
   Verified working (HTTP 200, correct nine-field JSON output): `gemini-flash-lite-latest`
   (recommended — stable alias that won't be retired out from under a pinned version) or
   `gemini-3.5-flash-lite`. No code change required; the model is intentionally configurable.

2. **Aging fallback default model.** `DEFAULT_MODEL` in `backend/app/extraction/config.py` is
   `gemini-2.0-flash`. It only applies when `GEMINI_MODEL` is unset. Optional future one-line
   follow-up: update the default to `gemini-flash-lite-latest` so a fresh clone without
   `GEMINI_MODEL` doesn't risk the same class of issue. Not changed here.

3. **Sandbox-only network note.** During verification, `/analyze` outcomes depended on outbound
   access to `generativelanguage.googleapis.com`. On a machine with internet and a valid key +
   available model, `/analyze` completes normally.

4. **Deprecation warnings (benign).** Two framework-level deprecation warnings appear in the
   backend test output (Starlette/httpx, anyio). They are pre-existing and unrelated to app code.

No open defects in application code. Item 1 is a required local `.env` change to make `/analyze` work.

---

## 7. Exact next steps

### A. Make `/analyze` work locally (required)
1. Edit `backend/.env` and set an available model:
   ```
   GEMINI_MODEL=gemini-flash-lite-latest
   ```
   (or `gemini-3.5-flash-lite`). Ensure `GEMINI_API_KEY` is set and `backend/.env` is not committed.
2. Restart the backend (command below) and run Analyze from the frontend; confirm a real analysis
   returns instead of the error.

### B. Verification (run before considering the build final)
From `backend/`:
```
.\venv\Scripts\python.exe -m pytest -q
```
Expect `368 passed`.

From `frontend/`:
```
npm run test
npm run build
```
Expect `49 passed` and a successful production build.

Runtime smoke test:
- Start backend, then `GET http://localhost:8000/api/health` → 200 `{"status":"ok"}`.
- With a valid key + available model, `POST /api/handoff/analyze` → 200 with `{handoff, validation}`.
- Frontend loop: input → Analyze → Results → (clarify → apply, returns to Results even if READY) →
  explicit "Format handoff" → Copy → "Start another handoff".

### C. Run locally (development)
- **Backend** (from `backend/`):
  ```
  .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
  ```
- **Frontend** (from `frontend/`, start after the backend):
  ```
  npm run dev
  ```

### D. Deployment considerations (not yet implemented)
Deployment is out of scope of the completed specs; the following are the outstanding items to
address when deploying:
- Serve the frontend production build (`frontend/dist`) via a static host/CDN; point it at the
  backend origin. In production the dev proxy does not apply — configure the API base URL or a
  reverse proxy so the frontend's relative `/api/*` calls reach the backend (or enable CORS on the
  backend for the frontend origin).
- Run uvicorn behind a production ASGI setup (e.g., a process manager / reverse proxy) without
  `--reload`.
- Provide `GEMINI_API_KEY`, `GEMINI_MODEL`, and `GEMINI_TIMEOUT_SECONDS` via the deployment
  environment (secret manager / env vars), never a committed file.
- Confirmed non-goals (intentionally absent, no action needed unless product scope changes):
  authentication, database, persistence/sessions, rate limiting, analytics.

---

## 8. Scope boundaries (intentional non-goals)

No database, authentication, sessions/persistence, RAG/vector search, agents/multi-agent
frameworks, custom ML/fine-tuning, or unnecessary dependencies. The frontend contains no business
logic — it renders backend results and never computes readiness. AI is used only for extraction
(and, per the clarification spec, is not required for clarify/apply/format).
