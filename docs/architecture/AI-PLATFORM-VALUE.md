# What the Foundry path gives that a gateway does not

Two ways to reach a model are supported ([AI-GATEWAY.md](AI-GATEWAY.md)): the
**Foundry** path, where each agent is a versioned prompt agent in a Foundry project,
and the **gateway** path, an OpenAI-compatible endpoint the customer already runs.
Both satisfy the same port and sit in the same provider chain, and the product's
guarantees — the engine computes every figure, nothing identifiable leaves under the
egress rule, every call is observed and audited — hold on either.

This page is the honest difference, for a customer deciding which to choose first.
Everything stated about Foundry is taken from Microsoft's own documentation, cited
below; where we have not verified a capability against the current service it is
marked **[verify]** rather than asserted.

## Source

[What is Microsoft Foundry Agent Service?](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)
(Microsoft Learn, updated 26 Oct 2026). Statements below that come from it are
marked †.

## Only on the Foundry path

| Capability | What it is | Gateway equivalent |
| --- | --- | --- |
| Managed runtime for prompt agents † | Foundry hosts and runs an agent defined by instructions, a model and tools — no code or containers to operate | None. The product sends the instructions with each request |
| Versioned agents † | "Version agents, create stable endpoints" — an agent version is immutable. This product records the version on every audit row and can pin one (`AI_AGENT_VERSION_PINS`) | The prompt **file** version (manifest-checked) is recorded instead; there is no server-side version to roll back to |
| Platform observability † | End-to-end tracing, metrics, evaluations and Application Insights integration in the Foundry portal | Our own spans and metrics (`gen_ai.*`) carry the same shape and land in the customer's Application Insights; evaluations are ours (`scripts/ai-eval.py`) |
| Content filters and Entra identity † | Microsoft Entra identity, RBAC and content filters on the agent | The customer's gateway applies its own policy; our `OutputPolicy` and prompt-injection guard apply on both paths |
| Network isolation † | Virtual networks and bring-your-own resources | Depends on the gateway's own network path ([AI-GATEWAY.md](AI-GATEWAY.md) lists the requirements) |
| Publishing † | Share an agent through Microsoft Teams, Microsoft Copilot and the Entra Agent Registry | Not applicable; the product's own Microsoft 365 channel is the route to those surfaces |
| Agent optimizer † (preview) | Evaluates agent behaviour and proposes better instructions and model choices | None. Prompt changes here go through the manifest and a version bump |
| Model catalog † | "Swap models without changing your agent code" within the Foundry model catalog | The customer's gateway chooses; our `AI_MODEL_*` settings name the model per role |

## Only on the gateway path

| Capability | Why it matters to a customer |
| --- | --- |
| Models Foundry does not host, or ones the customer has already approved | The customer's existing model governance and contracts apply unchanged |
| The customer's own rate limits, quotas, logging and chargeback | One place, already audited, already budgeted |
| No Foundry project dependency | A tenant that cannot use Foundry can still run the narrator |

The product's own controls — token budget, egress rule, retry/breaker/bulkhead,
telemetry that carries no text — apply to both, so choosing the gateway does not
mean choosing weaker guard rails.

## Bring your own model through Foundry

A third route exists: a Foundry **model connection** to the customer's endpoint, so
the agent stays a Foundry prompt agent but the model call goes to their service
(`foundry_connection` in the provider chain). Limits are in
[AI-GATEWAY.md](AI-GATEWAY.md). Which gateway shapes a Foundry connection supports
today **[verify]** against the current connection documentation before promising it.

## What neither path changes

No figure is produced by a model ([ADR-004](ADR-004-agentic-workflows.md)); the portal
chat path still streams prose that is not number-checked, while the Microsoft 365
channel validates it ([ADR-008](ADR-008-channel-numeric-integrity.md)). A customer
choosing a path is choosing where the words come from, not whether the numbers are
the engine's.
