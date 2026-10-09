# ADR-004 — Production agentic workflows on Foundry and MAF

**Date** 2026-08-25 · **Status** Accepted

## Context

The current agent layer is honest and limited. Nine agents are registered in
Azure AI Foundry as `PromptAgentDefinition`s with no tools attached; a Python
keyword router in `api/chat.py` matches one of five intents and runs a fixed
linear pipeline, feeding each agent a JSON brief and streaming its prose back.

Three limits matter for a production build:

1. **The router is a switch statement.** Five intents, matched on substrings.
   Anything outside them falls through to a default.
2. **Nothing is durable.** A pipeline is an async generator inside one HTTP
   request. If the connection drops, the work is gone. Nothing can pause for a
   human and resume.
3. **The numeric guarantee is weaker than we have been saying.** Registering no
   tools prevents an agent *computing* a number. It does not prevent an agent
   *misstating* one: `api/chat.py` puts canonical figures into the prompt and
   streams the model's prose to the UI unchecked. For narration that is
   tolerable. For an agent-drafted auditor memo it is not.

Microsoft Agent Framework 1.8.0 is present and provides what is needed:
`WorkflowBuilder` with `FanOutEdgeGroup`, `FanInEdgeGroup` and
`SwitchCaseEdgeGroup`; `CheckpointStorage` and `WorkflowCheckpoint`; and
`AgentMiddleware` / `ChatMiddleware` / `FunctionMiddleware`.

## Decision

### 1. MAF workflows replace the keyword router

Each business process becomes a `Workflow` built with `WorkflowBuilder`, with
`Executor` nodes and typed edges. Deterministic work stays in Python executors
that call domain services; agent nodes narrate and classify only.

Initial workflows:

| Workflow | Shape |
| --- | --- |
| `eligibility_run` | linear: load snapshot → calculate → narrate |
| `exception_triage` | fan-out over anomaly clusters → propose per cluster → fan-in → single proposal batch |
| `scenario_evaluation` | parse → **confirm (checkpoint)** → evaluate → compare → narrate |
| `rules_ingestion` | retrieve → extract → diff against current pack → propose |
| `evidence_authoring` | gather trail → draft → **validate numerics** → assemble |
| `opportunity_scoring` | fan-out over prospects → score → fan-in → rank |

The keyword router is retained as a **fallback** for the five known intents. A
planner that fails must degrade to something that works rather than fail the
demo.

### 2. Checkpointing is how a human enters the loop

The proposal pattern — *the agent proposes, the human disposes* — needs a
workflow that can stop for hours and resume intact. `CheckpointStorage` gives
exactly that.

```
run workflow ──▶ reaches an approval node
                        │
                 checkpoint + persist the proposal (Warehouse, ADR-007)
                        │
                 HTTP request ends. Nothing is in flight.
                        │
              …human reviews, hours or days later…
                        │
                 DecideProposal command (ADR-003)
                        │
                 rehydrate from checkpoint, resume with the decision
```

Two consequences worth naming. The approval becomes a durable, queryable record
rather than a callback — which is what an auditor needs. And the workflow cannot
proceed past an approval node without one, structurally, rather than by an `if`
somebody could remove.

Checkpoints are stored per tenant. A production `CheckpointStorage` implementation
backed by the Fabric Warehouse ([ADR-007](ADR-007-warehouse-operational-store.md))
would sit behind the same port pattern as everything else in ADR-002; none is
built yet. `FileCheckpointStorage` serves local development.

### 3. Middleware is where the numeric guarantee becomes real

This is the part that closes the gap in §3.1 of the handoff spec, and it is the
reason MAF earns its place over hand-rolled orchestration.

**`NumericIntegrityMiddleware`** (a `ChatMiddleware`) wraps every agent
invocation:

- Before the call, it records the canonical facts supplied in the brief.
- After the call, it extracts every numeric token from the model's output and
  checks each against those facts within a tolerance of zero.
- A figure that does not match a supplied fact is a **hard failure**, not a
  warning. The response is rejected and the workflow surfaces the discrepancy.

Two supporting rules make this tractable:

- Agents are instructed to reference figures by placeholder token
  (`{{net_new_headcount}}`) rather than retyping them, and the presentation layer
  substitutes canonical values. Middleware then verifies no stray numerals
  appeared.
- For any agent-authored artifact shown to a customer — F5.6 evidence
  authoring above all — the agent returns **structured output**, and numeric
  fields are compared field-by-field against the tool result before rendering.

Alongside it:

| Middleware | Job |
| --- | --- |
| `TenantScopeMiddleware` | Asserts every agent call carries a tenant context; refuses if absent |
| `PromptInjectionMiddleware` | Treats payroll text, statute text and web-retrieved content as untrusted; strips instruction-shaped content before it reaches a prompt |
| `TelemetryMiddleware` | Span per agent call into App Insights, with token counts and latency |
| `CostGuardMiddleware` | Per-tenant token budget; refuses rather than silently overspending |

`PromptInjectionMiddleware` is not theoretical here. `rules_ingestion` retrieves
statutory text from the public web and puts it in front of a model that proposes
rule-pack changes. That is a direct injection path into the numbers on a tax
return, and it needs a guard.

### 4. Agents may still hold no tools

Unchanged and reaffirmed. Foundry agents remain `PromptAgentDefinition`s. MAF
executors call domain services in Python; results enter the prompt as structured
briefs. The model classifies, plans and narrates. It never computes.

The distinction ADR-004 adds: previously that was the *whole* guarantee.
Now it is one of three, alongside numeric validation and structured output.

### 5. Managed Identity throughout

`DefaultAzureCredential` with a user-assigned managed identity — already
provisioned in `infra/main.bicep` with `Cognitive Services User` and
`Azure AI Developer` role assignments. No keys, no connection strings, no
secrets in configuration. Extend the same identity to the Fabric Warehouse and
Lakehouse (workspace role plus T-SQL grants).

## Consequences

**Good.** Long-running and human-gated processes become durable and resumable.
The numeric guarantee becomes a mechanism rather than an argument. Cross-cutting
agent concerns — tenancy, injection, cost, telemetry — are applied uniformly
instead of per pipeline. Workflow graphs are inspectable, which is what makes
the "show the plan before executing it" demo moment possible.

**Costs.** MAF workflow definitions are more ceremony than an async generator.
Checkpoint storage is state that must be versioned — a workflow shape change can
strand in-flight checkpoints, so checkpoints carry a workflow version and an
incompatible one is failed loudly rather than resumed wrongly.

**Risk.** `NumericIntegrityMiddleware` will produce false positives on legitimate
prose ("the first quarter", "one of three sites"). Mitigate by validating against
a supplied-facts allowlist and tokenised placeholders rather than by scanning all
numerals blind. Get this wrong in the strict direction, not the permissive one:
a rejected sentence is an inconvenience, a wrong figure on a return is not.
