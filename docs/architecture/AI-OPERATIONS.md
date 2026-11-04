# AI operations

How to run the model side of the product: what to watch, what to do when it
misbehaves, and how to change a prompt or a model safely. Design is in
[AI-GATEWAY.md](AI-GATEWAY.md) and [AI-RESILIENCE.md](AI-RESILIENCE.md); variables in
[ENV-VARS.md](ENV-VARS.md). The engine answers without a model, so every incident
below is about prose, not figures.

## What is observed

Every model call, on every provider, outermost in the stack, produces:

- **A span** named `chat` (`chat <model>` when the model is known), kind CLIENT, with
  the OpenTelemetry GenAI attributes: `gen_ai.operation.name`, `gen_ai.provider.name`
  (our provider name: `foundry`, `foundry_connection`, `gateway`), `gen_ai.agent.name`,
  `gen_ai.response.model`, `gen_ai.usage.input_tokens` / `output_tokens`,
  `gen_ai.response.finish_reasons`, `error.type` (the exception **class**), plus
  `tcc.role`, `tcc.outcome` (`ok` | `error` | `cancelled` | `abandoned`),
  `tcc.prompt_chars`, `tcc.output_chars`, `tcc.agent_version`, `tcc.estimated_usage`.
- **Metrics** `gen_ai.client.operation.duration` (s) and `gen_ai.client.token.usage`
  (by `gen_ai.token.type`), and counters `ai.retries`, `ai.breaker_opens`,
  `ai.bulkhead_rejections`, `ai.budget_refusals`.

**What is never recorded:** prompt text, reply text, instructions, employee or record
identifiers, or a hash of any of them. Attributes pass through an allow-list, so a
new keyword is dropped rather than recorded; `tests/test_ai_telemetry.py` plants
sentinels in every input and proves none reaches a span or metric.

With `APPLICATIONINSIGHTS_CONNECTION_STRING` set these flow to Application Insights
through the existing Azure Monitor configuration; with it unset the OpenTelemetry
API is a no-op.

Starting-point queries (client spans land in `dependencies`; confirm column names in
your workspace before building alerts on them):

```kusto
// Call outcomes by provider, last day
dependencies
| where timestamp > ago(1d) and customDimensions["gen_ai.operation.name"] == "chat"
| summarize calls = count(), p95_ms = percentile(duration, 95)
    by provider = tostring(customDimensions["gen_ai.provider.name"]),
       outcome = tostring(customDimensions["tcc.outcome"])
```

```kusto
// Retries, breaker openings and refusals
customMetrics
| where name startswith "ai." and timestamp > ago(1d)
| summarize total = sum(value) by name, provider = tostring(customDimensions["provider"])
```

## Health

`/api/health` carries an `ai` object: overall `ready` | `degraded` | `disabled`, each
provider's state, and how many Foundry agents are published. `/api/ready` never
depends on it. An open breaker reads `unavailable`; a half-open one `degraded`.

## Suggested alerts

| Signal | Meaning | First look |
| --- | --- | --- |
| `ai.breaker_opens` > 0 | A provider failed repeatedly and is being skipped | The provider's own status; the `error.type` on recent spans |
| `ai.budget_refusals` > 0 | A daily ceiling was hit | Whether the ceiling is right, or a client is looping |
| Share of `tcc.outcome = error` above a threshold | Model trouble | `error.type`: `ModelAuth` = credential, `ModelRateLimited` = quota, `ModelUnavailable` / `ModelTimeout` = the service |
| `ai.bulkhead_rejections` rising | Concurrency ceiling reached | `AI_BULKHEAD_MAX_CONCURRENT`, or a slow provider holding calls |
| Token usage `estimated` | A provider reports no usage, so budgets are approximate | Expected for some gateways; see `AI_TOKEN_BUDGET_*` |

## Changing a prompt

1. Edit `backend/agents/prompts/<agent>.md`.
2. Bump `version:` in its front matter and add a changelog line `N: why`.
3. `python scripts/prompt-manifest.py --refresh` (it refuses if you did not bump).
4. `python scripts/ai-eval.py` — and `--live` against a non-production project before
   promoting.
5. The test suite fails if the text changed without 2–3, so this cannot be skipped.

On startup Foundry publishes a new agent version only when the text differs. To go
back, pin the earlier version ([AI-RESILIENCE.md](AI-RESILIENCE.md)).

## Evals

`backend/tests/ai_evals/` holds three datasets and the thresholds:

| Suite | Offline (CI) checks | Live (`TCC_AI_EVALS_LIVE=1`) checks |
| --- | --- | --- |
| routing | The keyword fallback names exactly the right capabilities, and a row's `forbidden` capability is never named (a question about one client must not reach the whole-book ranking) | The router model's JSON plan |
| narration | The numeric guard rejects every recorded bad reply (changed digit, invented count, projection, rate) and passes the good ones. Rows with a `narration` (placeholders) run through the channel composer: a hedged figure (`roughly {{...}}`, `not rounded`, `up to`) must be dropped by the composer, and a kept narration must match its `must_contain` patterns and none of the forbidden wording (hedges, rank prose such as `position 1`) | Real narrations of the same briefs must all pass the guard |
| refusal | A question needing a client is refused or split when none is selected | Same (deterministic) |

Offline thresholds are 1.0 because those paths are deterministic; live thresholds
allow for model variance. Add a row when an incident shows a gap — the dataset is the
regression memory. Run `python scripts/ai-eval.py --json report.json` to keep a
record per release.

## Runbooks

**The assistant says it is unavailable.** Check `/api/health` → `ai.providers`. If a
breaker is open the provider is failing; the breaker re-probes every
`AI_BREAKER_RESET_SECONDS`. The reader still has the engine's figures. Look at
`error.type` before restarting anything.

**Narration quality regressed.** Find the `agent_version` on the audit rows around
the change, compare with the prompt manifest's history, pin the previous version,
then fix forward with the evals.

**Costs jumped.** `gen_ai.client.token.usage` by agent and provider; set
`AI_TOKEN_BUDGET_DAILY` / `_PER_PRINCIPAL_DAILY` as a guard rail while investigating.

**A customer's gateway changed.** `scripts/mock-ai-gateway.py` reproduces the dialect
and faults locally ([AI-GATEWAY.md](AI-GATEWAY.md)); extend the mock, then the
adapter, with a contract test first.
