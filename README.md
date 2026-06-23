# Avis Servicing Agent

An AI agent that services Avis Budget Group reservations against the mock API,
built on the OpenAI Agents SDK. The repo is structured as a **workflow registry**:
shared plumbing (API client, RAG, verification, error handling) plus one module
per workflow. **Cancel** and **upgrade** are the two workflows I focused on,
built out and validated against the live API. **Extend** and **modify** are also
enabled and runnable, but I treat them as drafts: the client and tools are wired,
yet I haven't fully built out or tested their conversation flows, so they're not
production-ready.

## Why Cancel first

Of the four workflows, cancel is the cleanest first build: only two API calls,
email-only verification (no payment details), and no dependency on the flaky
availability lookup. It set the pattern (verify, inform, confirm, execute,
close) that the other workflows reuse.

## Workflow status

| Workflow | Status | Notes |
|---|---|---|
| cancel | **stable** | Enabled; validated against the live API. |
| extend | draft | Enabled and runnable, but the conversation flow isn't fully built out or tested. |
| modify | draft | Enabled and runnable, but not fully built out or tested; also depends on the less-reliable `/availability`. |
| upgrade | **stable** | Client + tools wired; eligibility-gated outcomes handled. |

All four workflows are currently registered in `ENABLED` in
[`src/workflows/__init__.py`](src/workflows/__init__.py), so the live agent can
run any of them. `STATUS` is just a maturity label (stable vs draft), not a
switch: drop a module from `ENABLED` to take it offline.

## Where I focused, and why extend & modify stay draft

I focused on **cancel** and **upgrade**. **Extend** and **modify** are wired and
enabled so you can exercise them, but I deliberately did not invest in making
them production-ready. Both move money and carry risks I don't think an agent
should own yet:

- **Payment data in the wrong places.** They need CVV and billing ZIP, which
  arrive as conversation text, flowing into model context and logs. That's a
  PCI red flag before a single charge is processed.
- **A real double-charge window.** The idempotency key I generate covers the
  client's own retries, *not* a user saying "try again" across turns, so a
  repeated request can charge twice.
- **Concurrency with no coordination.** Each is a multi-call sequence (lookup,
  quote, write). In a live queue, a human or another AI agent can be working
  the same reservation at the same time; the calls conflict, everyone acts on
  stale state, and the agent can't tell it happened, exactly when it matters
  most.

**Cancel** and **upgrade** avoid this: each is in and out in two calls, with no
payment details and no real conflict window, which is why I built and validated
those two. Extend and modify open a window that's hard to close without
coordination infrastructure that doesn't exist yet, so I'd want a human in the
loop before trusting them in production.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # then fill in the keys (see below)
```

Required in `.env`:

- `AVIS_API_KEY`: from the 1Password link in `BRIEF.md`
- `AVIS_API_URL`: pre-filled
- `OPENAI_API_KEY`: your own key, with available quota/credits

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
| `src/rag.py` | Keyword/TF-IDF search over `data/knowledge-base/articles.json`. Title hits weighted 2×, stop-words stripped, IDF down-weights common terms. No vector DB; ~30 short articles don't need one. |
| `src/agent_common.py` | Cross-workflow building blocks: `error_payload` / `safe_call` (turn HTTP errors into structured dicts), `reservation_timing` (code-computed 48h window), and the two shared tools every workflow uses (`lookup_reservation`, `search_knowledge_base`). |
| `src/workflows/` | One module per workflow, each exposing a uniform `NAME / STATUS / TOOLS / INSTRUCTIONS`. `__init__.py` is the registry that assembles enabled workflows. |
| `src/agent.py` | Builds the agent from the registry (shared tools + enabled workflows' tools and instructions) and runs the `main()` loop, preserving history via `result.to_input_list()`. |

### Conversation flow

Both focus workflows (**cancel** and **upgrade**) share the same shape; the
Inform/Execute/Close steps specialize per workflow.

1. **Identify**: ask for the reservation ID, call `lookup_reservation` (upgrade
   also reads `customer_id` and `membership_status` from the result).
2. **Verify**: ask for the email on file (the agent never hints at it).
3. **Inform**: pull the relevant policy from the KB and set expectations.
   - *Cancel:* explain the penalty that applies, using a derived
     `cancellation_timing` block (hours-until-pickup and the 48-hour window)
     computed in code, not by the LLM.
   - *Upgrade:* explain that Preferred is eligibility-based (rental history),
     not a vehicle-class change; if already Preferred, say so and stop.
4. **Confirm**: explicit "do you want to proceed?" before any write.
5. **Execute**: call the workflow's write tool (`cancel_reservation_tool` or
   `upgrade_customer_tool`) with a fresh idempotency key.
6. **Close**: report the outcome.
   - *Cancel:* confirmation number, penalty, refund amount, 5 to 10 day timeline.
   - *Upgrade:* on success, new Preferred status and benefits; on
     `NOT_ELIGIBLE` / `ALREADY_PREFERRED` / `CUSTOMER_NOT_FOUND`, explain the
     outcome kindly.

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
