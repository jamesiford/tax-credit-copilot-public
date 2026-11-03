# Demo cleanup: what to switch off after a demo

The Microsoft 365 channel demo runs with a deliberately open posture so people can try it. None of it
belongs in a deployment that holds real payroll. Switch these off **in this order**, each one a small,
reversible step. Nothing here is run by the repository's code or by CI; an operator runs it.

Two kinds of setting are involved, and the commands differ:

- **Mapped values** are read from the azd environment, so `azd env set` changes them
  (`infra/main.tfvars.json` maps them).
- **Unmapped Terraform variables** are not in `infra/main.tfvars.json`; the demo sets them in the
  gitignored overlay `infra/m365-poc.auto.tfvars`. Edit the line there, then provision. There is no
  `azd env set` for these, because mapping a list or a diagnostic switch into every environment is
  how a demo setting becomes a default.

Run from the repository root unless a step says otherwise. Each `azd provision` should end with a plan
that changes only what that step names.

## 1. Debug whoami (the diagnostic commands)

`CHANNEL_DEBUG_WHOAMI` offers `/whoami`, `/netcheck` and `/modelprobe` on the orchestrator and the
`channel_ping` tool on the gateway. Both processes log a **WARNING at startup** while it is on, and
default to off everywhere a default exists.

Orchestrator (the hosted agent), from its own project:

```pwsh
cd channel_orchestrator
azd env set CHANNEL_DEBUG_WHOAMI false
azd deploy
```

That creates a new agent version. If the published app does not follow the latest version, republish it
([PUBLISHING](PUBLISHING.md)).

Gateway: in `infra/m365-poc.auto.tfvars` set (or delete the line, since `false` is the default):

```hcl
channel_debug_whoami = false
```

```pwsh
azd provision --no-prompt
```

Check: send `/whoami` to the agent. It must be answered as an ordinary question, not with identity
signals.

## 2. The open Foundry firewall

The demo admits the hosted runtime by opening the Foundry data plane to any address
(`foundry_allow_any_ip`) with a public network. Close both:

```pwsh
azd env set TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS false
azd env set TCC_FOUNDRY_ALLOWED_IP_RANGES ""
```

and in `infra/m365-poc.auto.tfvars`:

```hcl
foundry_allow_any_ip = false
```

```pwsh
azd provision --no-prompt
```

After this the workstation cannot deploy or publish agents; the real fix is in
[HARDENING-PLAN](../architecture/HARDENING-PLAN.md).

## 3. Allowed caller app ids

`channel_allowed_caller_app_ids` lets an orchestrator call the gateway **without** the `Channel.Invoke`
role (a sandbox where the role could not be assigned). Remove it and rely on the role. In
`infra/m365-poc.auto.tfvars`:

```hcl
channel_allowed_caller_app_ids = []
```

First confirm the agent identity holds the role (`scripts/assign-channel-roles.ps1`, see
[OPERATIONS](OPERATIONS.md)), then:

```pwsh
azd provision --no-prompt
```

Check: a call from the agent still succeeds; the gateway log line "caller authorised" shows the role
path, not the allow-list.

## 4. The mock model gateway

The mock OpenAI-compatible gateway is a proof-of-concept tool that validates token shape, not
signatures. In `infra/m365-poc.auto.tfvars`:

```hcl
enable_mock_ai_gateway = false
```

Also point the model settings back at Foundry (or at the customer's real gateway) first, so nothing
still names the mock. The platform API's chain is a Terraform variable (`ai_provider_chain`), and the
orchestrator's is an azd value in its own project:

```hcl
ai_provider_chain = "foundry"
```

```pwsh
azd provision --no-prompt
cd channel_orchestrator
azd env set AI_PROVIDER_CHAIN foundry
azd deploy
```

## 5. The group-based writer source

The demo may let an Entra group, in addition to the allow-list, decide who may change records. Return
to the allow-list only, then review who is on it:

```pwsh
azd env set TCC_CHANNEL_WRITER_SOURCE allowlist
azd env set TCC_CHANNEL_WRITER_GROUP_ID ""
azd provision --no-prompt
python scripts/channel-writers.py list
python scripts/channel-writers.py remove <object-id>   # each demo operator who should not keep write access
```

People who were writers only through the group can read afterwards but not change records. The Graph
`GroupMember.Read.All` grant to the gateway and API identities is no longer needed once the group
source is off; revoke it if nothing else uses it.

## After all five

```pwsh
terraform -chdir=infra plan -detailed-exitcode   # 0: nothing left to change
pwsh scripts/channel-smoke.ps1 -Since (Get-Date).AddMinutes(-15)
```

Then re-read [KNOWN-LIMITATIONS](KNOWN-LIMITATIONS.md), "The demo posture is public", and decide whether
the gateway's public reachability is acceptable for what you do next.
