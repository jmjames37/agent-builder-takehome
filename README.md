# Avis Servicing Agent

An AI agent that services Avis Budget Group reservations against the mock API,
built on the OpenAI Agents SDK. The repo is structured as a **workflow registry**:
shared plumbing (API client, RAG, verification, error handling) plus one module
per workflow. **Cancel** is fully built and validated; **extend / modify /
upgrade** are wired end to end at the client layer and scaffolded as draft
workflow modules ready to enable.

## Why Cancel first

Of the four workflows, cancel is the cleanest first build: only two API calls,
email-only verification (no payment details), and no dependency on the flaky
availability lookup. It set the pattern (verify → inform → confirm → execute →
close) that the other workflows reuse.

## Workflow status

| Workflow | Status | Notes |
|---|---|---|
| cancel | **stable** | Enabled; validated against the live API. |
| extend | draft | Client + tools wired and live-tested; quote-before-charge flow drafted. |
| modify | draft | Client + tools wired; depends on the less-reliable `/availability`. |
| upgrade | **stable** | Client + tools wired; eligibility-gated outcomes handled. |

Enable a draft workflow by adding its module to `ENABLED` in
[`src/workflows/__init__.py`](src/workflows/__init__.py) — the agent picks up its
tools and instructions automatically.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # then fill in the keys (see below)
```

Required in `.env`:

- `AVIS_API_KEY` — from the 1Password link in `BRIEF.md`
- `AVIS_API_URL` — pre-filled
- `OPENAI_API_KEY` — your own key, with available quota/credits

> **Python version:** the OpenAI Agents SDK targets Python 3.10+. If you're stuck
> on 3.9 (e.g. macOS system Python), the `eval_type_backport` package in
> `requirements.txt` makes the SDK importable there. Python 3.12 is recommended.

## Run

```bash
python src/agent.py          # interactive cancellation session
python src/avis_client.py    # smoke-test API connectivity
python src/rag.py            # smoke-test knowledge-base retrieval
```

## Architecture

| File | Responsibility |
|---|---|
| `src/avis_client.py` | API client covering **all** endpoints (reservation, availability, quote, cancel, extend, modify, upgrade). One shared transport: bounded exponential backoff + jitter on 5xx/timeouts (max 3), per-write UUID `Idempotency-Key`, structured logging. 4xx are never retried. |
| `src/rag.py` | Keyword/TF-IDF search over `data/knowledge-base/articles.json`. Title hits weighted 2×, stop-words stripped, IDF down-weights common terms. No vector DB — ~30 short articles don't need one. |
| `src/agent_common.py` | Cross-workflow building blocks: `error_payload` / `safe_call` (turn HTTP errors into structured dicts), `reservation_timing` (code-computed 48h window), and the two shared tools every workflow uses (`lookup_reservation`, `search_knowledge_base`). |
| `src/workflows/` | One module per workflow, each exposing a uniform `NAME / STATUS / TOOLS / INSTRUCTIONS`. `__init__.py` is the registry that assembles enabled workflows. |
| `src/agent.py` | Builds the agent from the registry (shared tools + enabled workflows' tools and instructions) and runs the `main()` loop, preserving history via `result.to_input_list()`. |

### Conversation flow

1. **Identify** — ask for the reservation ID, call `lookup_reservation`.
2. **Verify** — ask for the email on file (the agent never hints at it).
3. **Inform** — pull cancellation policy from the KB and explain the penalty
   that applies, using a derived `cancellation_timing` block (hours-until-pickup
   and the 48-hour window) computed in code, not by the LLM.
4. **Confirm** — explicit "do you want to proceed?" before any write.
5. **Execute** — `cancel_reservation_tool` with a fresh idempotency key.
6. **Close** — confirmation number, penalty, refund amount, 5–10 day timeline.

### Error handling

Tools catch `requests.HTTPError`/network errors and return structured dicts
(`{error, status, code, message}`) instead of raising, so the agent recovers in
natural language:

| Code | Behavior |
|---|---|
| `VERIFICATION_FAILED` (403) | Ask to re-check the email; after 2 failures, direct to call Avis. |
| `RESERVATION_NOT_FOUND` (404) | Ask to re-check the reservation ID. |
| `RESERVATION_NOT_ACTIVE` (409) | Note it may already be cancelled. |
| `5xx` / timeout | Retried with backoff in the client; if still failing, apologize and suggest retry / calling Avis. |

## Logging

All API calls (endpoint, reservation ID, idempotency key, response status) and
every user/agent turn are logged to **`agent.log`** in the repo root and to
stdout.

## Test accounts

| Reservation | Email on file |
|---|---|
| `AVS-29471835` | `sarah.johnson@example.com` |
| `AVS-48372915` | `marcus.lee@example.com` |
| `AVS-77001020` | `priya.patel@example.com` |
| `AVS-66002030` | `david.kim@example.com` |
| `AVS-50000001` | `robert.chen@example.com` |
| `AVS-99004050` | `tomas.rivera@example.com` |

Writes are ephemeral on the mock — cancelling does not persist, so you can test
freely.
