# CLAUDE.md: rules for AI coding assistants working on this repo

Read this before changing anything. The plan behind these rules is in `docs/plan.md`.

## What this project is

A FastAPI + React assistant that answers questions about 2025 invoices and a procurement policy. **Every answer must be verifiable**: it shows the policy clauses and invoice rows it is based on.

## Non-negotiables

1. **The LLM never computes numbers.** Every sum, conversion, count and ranking happens in `backend/app/tools/` (pandas). If a new kind of question needs a new number, add or extend a tool. Never ask the model to calculate.
2. **Evidence is only created in `backend/app/evidence.py`.** The model returns clause IDs and query IDs; the server resolves them. Never let model output flow into the evidence fields.
3. **Every tool has tests**, checked against the independent reference in `backend/tests/reference.py`. The reference must never import from `app`.
4. **The API contract lives in two places that must match:** `backend/app/schemas.py` and `frontend/src/lib/types.ts`. Change both in the same commit.
5. **Prompt changes are versioned.** To change the system prompt, create `system_vN.md`, bump `PROMPT_VERSION` in `backend/app/llm/prompt.py`, and run the tests.
6. **Never log or return the API key** (`key_1`). It is read only in `backend/app/config.py` and used only in `backend/app/llm/client.py`.
7. **No new dependencies without a written reason** in the commit message. The backend uses FastAPI, pandas, pydantic and anthropic; the frontend uses React only.

## Conventions

- Python 3.11+, type hints everywhere, `from __future__ import annotations`.
- Each module starts with a plain-English docstring: what it does and why it exists. Keep it accurate when the code changes.
- Errors the user can see are subclasses of `AppError` in `backend/app/errors.py`, each with an HTTP status and a `code` that the frontend maps to a message (`frontend/src/lib/api.ts`).
- Frontend: function components and hooks, `useReducer` for chat state, plain CSS in `styles.css`, no UI library.
- Keep it readable before clever: this code is walked through line by line in an interview.

## Before you finish a change

```bash
cd backend && pytest            # must pass
cd frontend && npm run build    # type-checks and builds
```
