# The hosted orchestrator and the AI platform

What changed for the Microsoft 365 orchestrator (Prompt 4) because model access is now
a set of ports with a provider chain (AI-01 … AI-08). Read this before building it; it
replaces any earlier assumption that the orchestrator constructs its own Foundry or
model client.

## One AI contract, in the container

The orchestrator runs with the **same `AiSettings`** as the API: the same `AI_*`
variables ([ENV-VARS.md](../architecture/ENV-VARS.md) section 8) read by the same
`load_ai_settings`, so a customer who points the API at a gateway points the
orchestrator at it with the same settings, and the provider chain, per-role models,
egress policy, resilience and budgets behave identically. It must not read
`FOUNDRY_*` directly or build an `AIProjectClient`/`FoundryAgent` itself: SDK use is
confined to `infrastructure/ai/` (`tests/test_architecture_ai.py` fails the build
otherwise).

Compose it the way the API does — `application/ai_wiring.py` — and call the model only
through `NarrationService` (portal and channel both): `ChannelNarrationQuery` through
the mediator is the entry point built for it. That one path carries, in order:
injection screen → observed → egress → budget → bulkhead → breaker → retry → timeout
→ provider. Do not add a second route to a model.

## Vendored packages, not single files

The channel's checks are copied into the container, and several of them were split by
size in AI-08. Vendor **the files together**:

| Vendored unit | Files |
| --- | --- |
| Numeric guard | `application/numeric_guard.py`, `numeric_types.py`, `numeric_extract.py`, `numeric_context.py`, `numeric_facts.py` |
| Composer | `application/composer.py`, `composer_placeholders.py`, `composer_render.py` |
| Output policy | `application/output_policy.py` |
| Formatter | `application/capabilities/format.py`, `format_core.py`, `format_renderers.py` |
| Catalog and envelope | `application/capabilities/catalog.py`, `catalog_types.py`, `catalog_intents.py`, `envelope.py` |

Each imports only the standard library and the other files in this table (pinned by
`test_numeric_guard`, `test_composer` and `test_architecture`). Every import path is
unchanged, so `from application.composer import compose` works as before; the unit of
vendoring is now the package, and a new sibling is a vendoring change, not a code
change. Anything the orchestrator needs beyond these (the ports, settings, chain,
safety package) comes from the shared backend package, not from copies.

## Output safety is part of `compose`

`compose(…, allowed_hosts=…)` now applies `output_policy` to the narration after the
numeric guard (ADR-008): a link, address, identifier shape, code block, or
legal-advice claim drops the narration exactly as a bad figure does, and the violation
is returned for the audit row. Pass `AiSettings.safety.output_allowed_hosts` as
`allowed_hosts`. The orchestrator must send the reader's own text to a model through
`UntrustedText(...).fenced()`; the injection screen runs on whatever reaches the
service, and a flagged prompt is never sent (the reader gets the platform's blocks).

## JSON-plan mode when the gateway has no tool calling

The orchestrator was specified to let the model choose tools by tool calling. A
gateway may not support that (`AI_GATEWAY_SUPPORTS_TOOLS=false`); Foundry prompt
agents carry no tools by design (ADR-004). So the orchestrator has **two planning
modes**, selected from settings, with identical outcomes:

- **Tool-calling** (`supports_tools` true): the model is offered `ToolSpec`s built from
  the catalog and returns `ToolCall`s.
- **JSON plan** (`supports_tools` false, and always on Foundry prompt agents): the
  model returns `{"intents": [...]}` exactly as the portal router does
  (`api/chat/routing.py`), validated against `CAPABILITIES` — an invented name is
  dropped, never dispatched — and the orchestrator runs each capability itself.

In both modes the model chooses WHICH tool runs and never produces a figure; the
capability's own facts are the only source of one. Build JSON-plan first: it works on
every provider, and tool-calling is an optimisation, not a prerequisite.

## What the orchestrator inherits and must not re-implement

| Concern | Where it already lives |
| --- | --- |
| Provider order, fall-through, hop recording | `ProviderChain` |
| Timeout, retry, breaker, bulkhead | `infrastructure/ai/resilience/` |
| Token budget | `application/ai/budget.py` (per process: size it with the worker count) |
| Degraded answer when no model can narrate | the platform's own blocks (`compose` with no narration) |
| Egress rule (no record token, SSN shape or identifier key leaves) | `application/ai/egress.py` |
| Telemetry (GenAI spans and metrics, no text) | `infrastructure/ai/otel_telemetry.py` |
| Prompt text, versions and the drift check | `backend/agents/prompts/` and its manifest |

## Open questions for the owner

- Which gateway auth scheme, dialect and model names the customer will provide
  ([AI-GATEWAY.md](../architecture/AI-GATEWAY.md) lists the questions for the gateway
  team); the orchestrator's container needs the same settings and the same network
  path as the API.
- Whether the orchestrator replicas share a token budget. It is per process today; a
  shared store is the follow-up if a customer needs the ceiling exact.
