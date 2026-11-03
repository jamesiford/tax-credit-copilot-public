# Model access (M-01) and the silent Teams chat: live evidence, 3 November 2026

Sandbox only, synthetic data only. Identifiers are redacted; the private notes hold the real ones.

## 1. M-01: the hosted agent could not reach a model

**Method.** Two gated diagnostics were added to the orchestrator (`/netcheck`, `/modelprobe`, both behind
`CHANNEL_DEBUG_WHOAMI`) and called through the agent's own endpoint
(`.../agents/<name>/endpoint/protocols/openai/responses?api-version=v1`).

**Finding.** From inside the hosted runtime:

| Host | Result |
| --- | --- |
| `<account>.services.ai.azure.com` | `Temporary failure in name resolution` |
| `<account>.cognitiveservices.azure.com` | `Temporary failure in name resolution` |
| `<account>.openai.azure.com` | resolves, answers 401 without a token |

The documented client path (`AIProjectClient.get_openai_client()`) fails at the same DNS step. Why the runtime
resolves only the third name is not known; the Foundry firewall is open (Entra-only), so this is not an access rule.

**Fix.** The `foundry` provider calls `https://<account>.openai.azure.com/openai`. RBAC on the account: the agent's
instance identity holds Foundry User (inherited from the project) and, added in this prompt, Cognitive Services User
(`a97b65f3-24c7-4388-baec-2e87135dc908`) on the Foundry account. The identity is read from `GET /agents/<name>`
`instance_identity`, never assumed.

## 2. Two defects found once the model answered

1. The model dropped the `facts.` prefix from placeholders. The digits of the unresolved path (for example
   `clients.0`) counted as typed figures and the guard withheld the whole narration. Every `fact_paths` entry now
   carries an exact `placeholder` to copy. Test: `test_orch_placeholders.py`.
2. The planner chose `book_rank` for one-client questions. The planner prompt now separates one-client from
   whole-book questions.

A guard-rejected audit row (`narrate`, `guard=rejected`) was observed live before fix 1.

## 3. Acceptance

- A free-form whole-book question: model narration, every figure a resolved placeholder, `guard=pass`.
- Audit rows for it: `channel=teams`, `identity_assurance=channel-asserted`, `operation=narrate`, `guard=pass`.
- Prompts trying to make the model type a figure: the model declined to write digits. It did mis-describe one figure
  as "rounded". That is the documented limit: the guard compares values, not meaning.

## 4. The silent Teams chat

**Symptom.** `/whoami` delivered twice (1:05 PM and 1:34 PM PST), no reply. Azure Bot Service metrics showed HTTP 200
only.

**Evidence.** The container log of the Teams session shows `POST /activity/messages` answered 404. The agent
declared `activity` as a *container* protocol, so the platform posted Activities to a path nothing serves. The
sibling project's go-no-go (Run 35) records the same failure.

**Fix.** `activity` is declared on `agentEndpoint.protocols` only; the container protocol list is `responses`. Endpoint
authorization schemes are `Entra` and `BotServiceRbac`. The platform then bridges Activity to Responses.

| After deploy / publish | Expected | Observed (version 16) |
| --- | --- | --- |
| `definition.protocol_versions` | `responses` only | `responses` |
| `agent_endpoint.protocols` | `activity`, `responses` | `activity`, `responses` |
| `enable_m365_public_endpoint` | true | true |
| authorization schemes | `Entra`, `BotServiceRbac` | `Entra`, `BotServiceRbac` |

Re-checked after every deploy and after the re-publish (Shared scope, manifest 1.0.2, developer name 24 characters).

**What was not proven.** A direct Activity to the Activity Protocol URL returned HTTP 202, but the container receipt
could not be observed (the session list is incomplete). Web Chat is unavailable: the bot's public network access is
`Disabled`. The Teams proof needs the owner (DEMO-SCRIPT, "Retry in Teams").

## 5. Identity under the bridge

`x-agent-user-id` is a 36-character GUID equal to the caller's object id for a direct call. It is now a default
identity source (`agent-user-id`) and `/whoami` reports the *shape* of the header, never the value. The
`x-ms-user-identity` header is refused for direct callers ("not authorized to delegate"). Whether Teams supplies the
same signal under the bridge is unproven until the owner's Teams run.

## 6. RBAC and settings changed in this prompt

| Change | Scope | Why |
| --- | --- | --- |
| Cognitive Services User to the agent instance identity | Foundry account | the sibling project's working publish grants both roles |
| `CHANNEL_IDENTITY_SOURCES=original-subject,platform,agent-user-id` | agent azd env `tcc-orch` | D-102 |
| `MOCK_AUTH` changed to `api_key`, then `oauth`, then back to `entra` | mock gateway app setting | live provider-chain checks; `azd provision --preview` reports no changes after the restore |
