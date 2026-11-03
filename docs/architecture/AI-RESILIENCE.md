# AI resilience

How a model failing, slowing down or costing too much is kept from becoming the
reader's problem. [AI-04] The engine answers without a model — only the prose needs
one — so every rule below ends in "the reader still gets the engine's figures".

## The stack around every provider

```
GuardedRuntime        egress check → token budget           (application/ai/guarded.py)
  BulkheadRuntime     at most N concurrent calls
    BreakerRuntime    stop calling a provider that keeps failing
      RetryRuntime    backoff with jitter, honour Retry-After
        TimeoutRuntime   a quiet gap between events is a failure
          the provider (Foundry, Foundry connection, gateway, a fake)
```

Built once, in `application/ai_wiring._decorate`, for every provider — adding a
provider adds no resilience code. The decorators live in
`infrastructure/ai/resilience/` and take a `Clock`, so tests run on virtual time.

The order is the design:

| Layer | Why it sits where it does |
| --- | --- |
| Bulkhead outside breaker | Shedding load is not the provider being unwell, so it must not trip the breaker |
| Breaker outside retry | One request retried three times is one failure, not three; an open breaker stops retries being attempted |
| Retry outside timeout | A timed-out attempt is retried |
| Egress and budget outermost | A refused prompt is never retried, never counted against a provider |

## Rules, with defaults

| Behaviour | Rule | Setting (default) |
| --- | --- | --- |
| Timeout | Longest **gap between events**, not the whole call: a long healthy narration is not cut off | `AI_CALL_TIMEOUT_SECONDS` (30) |
| Retry | Only unavailable / timeout / rate-limited; **only before any text**; full-jitter exponential backoff capped at the max; `Retry-After` honoured | `AI_RETRY_MAX_ATTEMPTS` (3), `AI_RETRY_BASE_SECONDS` (0.5), `AI_RETRY_MAX_SECONDS` (8) |
| Total deadline | No retry that would end after this, measured across attempts | `AI_TOTAL_DEADLINE_SECONDS` (45) |
| Never retried | Bad request (any 4xx but 429), refused credential, egress refusal | — |
| Breaker | Opens after N consecutive provider failures; after the reset period lets **one** probe through; a request the provider rightly refused does not count | `AI_BREAKER_FAILURE_THRESHOLD` (5), `AI_BREAKER_RESET_SECONDS` (30) |
| Bulkhead | Past the limit a call is refused at once, not queued — the chain moves on | `AI_BULKHEAD_MAX_CONCURRENT` (8) |
| Budget | Daily UTC allowance, overall and per person; refused **before** the call; usage charged after (estimated at 4 chars/token, and marked as an estimate, when the provider reports none) | `AI_TOKEN_BUDGET_DAILY`, `AI_TOKEN_BUDGET_PER_PRINCIPAL_DAILY` (none) |

The budget is in memory and per process: with several workers the ceiling is
roughly the figure times the worker count. It is a guard rail, not an invoice.
A refusal is logged and counted (`ai.budget_refusals`) with the scope and provider,
never the prompt.

## What the reader sees

| Situation | Portal chat | Page summary |
| --- | --- | --- |
| Every provider failed before any text | "The assistant is unavailable; here are the engine's figures." plus the brief's values, unchanged (once per request; later agents show figures only) | The existing facts fallback |
| A provider failed **after** text began | The text already shown stays; "The assistant was interrupted; the engine's figures follow." plus the figures. The chain never splices a second model's sentences onto the first | The existing facts fallback |
| The reader disconnects | The partial output is recorded in the audit row as not-ok; the cancellation propagates | — |

The figures are the brief JSON the engine already produced, flattened to
`name: value` lines (at most 30, with a count of how many were left out). Nothing is
computed and nothing is a model's.

## Health

`/api/ready` never fails because of AI. `/api/health` reports each provider's state
(`ready`, `degraded`, `unavailable`, `disabled`); an open breaker shows as
`unavailable`, a half-open one as `degraded`. A deployed process **does** refuse to
start on a *misconfigured* AI setting (bad chain, gateway with TLS off or no auth) —
that is a configuration error, not an outage.

## Version pins and rollback

Foundry agent versions are immutable and the app publishes a new version only when
a prompt's text changes (identical definitions are reused). To run an earlier
version of an agent — for example after a prompt change regresses narration:

1. Find the version that was good. `StreamEnd.agent_version` is recorded on every
   `agent_action_audit` row, so the audit trail says which version answered when.
2. Set `AI_AGENT_VERSION_PINS=ReportingAgent=3,ClientSituationAgent=2` on the API app
   and restart. A pinned agent is **fetched**, never created, so the pin cannot
   publish anything.
3. To undo, remove the setting and restart; the latest version resumes.

Rollback is a setting, not a deploy. A pin naming a version that does not exist
fails that agent's publish step (it is not registered, so the provider is not ready
for it and the chain moves on) rather than silently running another version.

Model changes roll back the same way: `AI_MODEL_<ROLE>[__<PROVIDER>]` names the
model per role, so reverting to the previous model is the previous value.

## Testing

`tests/test_ai_resilience.py` (every decorator on a `FakeClock`),
`tests/test_ai_budget.py`, `tests/test_ai_degraded.py`,
`tests/test_ai_startup_resilience.py` (startup with Foundry or the gateway
unreachable) and the fault-injection cases in `tests/test_ai_fallthrough.py` against
the mock gateway ([AI-GATEWAY.md](AI-GATEWAY.md)). The suite installs an
`InstantClock` so a retry never makes a test wait out a real backoff.
