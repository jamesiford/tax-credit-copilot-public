# Spike S6: prove the hardened Foundry path

**Status** Not run. Run after the demo. **Owner** the platform lead. **Decides** whether the hardened
posture in [HARDENING-PLAN](../architecture/HARDENING-PLAN.md) §3 can be built as written.

This is a checklist, not a design. Each step has a pass condition and a place to write what happened.
It exists because two things in the plan are **per the documentation, unproven**:

1. that a hosted agent in a network-isolated project needs only a delegated agent subnet and private
   endpoints, **not** the classic "standard agent setup" (Cosmos DB, AI Search, Storage and a capability
   host); and
2. that a hosted orchestrator in that subnet can reach a private gateway and a model deployment.

**The customer has ruled Cosmos DB out.** If a step cannot pass without Cosmos, a capability host or a
bring-your-own Search, the spike has **failed**: record the exact error, stop, and escalate. Do not add
Cosmos to make it work.

## Before you start

| | |
| --- | --- |
| A scratch resource group in a region that supports hosted agents and is the **same region as the VNet** | Not the demo environment: S6 creates a new Foundry account, because network injection cannot be added to an existing one |
| Resource providers registered by an operator: `Microsoft.App`, `Microsoft.ContainerService`, `Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.BotService` | Terraform never registers them |
| An operator with Owner on the scratch group, and Global Administrator active if an app role assignment is needed | |
| Synthetic data only | The demo posture's rules apply to the spike |
| The current Foundry documentation open (see the plan's source list) | The features are in preview; where it differs from the plan, the documentation wins and the plan is corrected |

## Checklist

Record against each step: **Pass / Fail / Blocked**, the exact command or portal action, and the
output (redacted: no tokens, no tenant or subscription ids in what you paste into the repository).

### S6.1 Network

- [ ] A VNet in the scratch group, an **agent subnet** (/24, delegated to `Microsoft.App/environments`, not
      shared, outside the reserved ranges in plan §3.2), a **private-endpoint subnet**, and the private DNS
      zones in plan §3.6, linked to the VNet.
- **Pass when** the subnet shows the delegation and size, and `nslookup` of each zone's names from inside the
  VNet (later, from the ops VM) returns a private address.

### S6.2 The account and project, with no Cosmos

- [ ] Create a Foundry account **with network injection**, in the same region as the VNet, public network
      access **off**, and a project. **Do not** create or reference a Cosmos DB account, an AI Search service,
      a storage account for agents or a capability host.
- **Pass when** the account and project reach "succeeded" with network injection set and no capability host.
- **Fail when** the service refuses to create the project, or to run an agent, without a capability host or
  bring-your-own Cosmos, Search or Storage. Record the exact error and its correlation id.

### S6.3 Ops host

- [ ] An ops VM in the VNet (no public IP) and Azure Bastion; a managed identity with the minimum roles.
- **Pass when** `az vm run-command invoke` runs a command on it, and from it a call to the account's data
  plane succeeds while the same call from your workstation **fails** (403 or no route).

### S6.4 A stub hosted agent, by source-code deployment

- [ ] From the ops VM, deploy the stub orchestrator (`channel_orchestrator/`, or its smallest echo form) by
      **source-code deployment**: no container registry.
- [ ] Call it over the Responses protocol from the ops VM.
- **Pass when** the agent answers, with no registry and no capability host.

### S6.5 The agent reaches a private gateway and a model

- [ ] A stub gateway on an App Service with a **private endpoint** and public access off.
- [ ] The agent, running in the delegated subnet, calls the stub gateway by its private name and a model
      deployment on the account.
- **Pass when** both calls succeed from the agent and the gateway's log shows the request arriving over the
  private path, with the agent identity's token validated.

### S6.6 Publish to Teams

- [ ] Publish with `enable_m365_public_endpoint` (the REST flow in `docs/m365-channel/PUBLISHING.md`,
      with the bot resource's `publicNetworkAccess` disabled), scope *Just you*, and send a Teams message.
- **Pass when** the message round-trips, and the audit shows the right person with `channel-asserted`.

### S6.7 Negative checks

- [ ] From your workstation, every Foundry data-plane call fails; the gateway answers only from inside.
- [ ] Cowork's connector is off (no public MCP) unless the restricted toggle is on.
- **Pass when** each fails as stated.

## Acceptance criteria

| | |
| --- | --- |
| **Spike passes** | S6.1 to S6.7 all pass, **with no Cosmos DB, no AI Search, no agent Storage and no capability host anywhere in the scratch group** |
| **Spike fails** | Any step needs one of those, or the agent cannot reach the private gateway or model. Escalate to Microsoft Foundry engineering and to the customer with the recorded errors. The fallback is the demo posture with `data_classification = synthetic` |
| **Spike is inconclusive** | A step is blocked by something other than the design (quota, region, a missing role). Say what, fix it, rerun that step |

On a pass, correct decision D-92 in [DECISIONS.md](DECISIONS.md) from "per the documentation" to
"proven by S6 on <date>", and start HD-02 onwards. On a fail, record it there and update the plan's §3.3.

## Results template

Copy this into a new file `docs/m365-channel/evidence/hardening-spike-<date>.md` (no identifiers; use
placeholders) and fill it in.

```markdown
# S6 results, <date>

Operator: <initials>   Region: <region>   Documentation read on: <date>

| Step | Result | What was done | Output / error (redacted) |
| --- | --- | --- | --- |
| S6.1 Network | | | |
| S6.2 Account and project, no Cosmos | | | |
| S6.3 Ops host | | | |
| S6.4 Stub agent, source-code deployment | | | |
| S6.5 Private gateway and model | | | |
| S6.6 Teams round trip | | | |
| S6.7 Negative checks | | | |

**Cosmos DB, AI Search, agent Storage or a capability host present anywhere?** Yes / No

**Verdict:** Pass / Fail / Inconclusive

**Differences from the plan:**

**Next step:**
```
