# Publishing the orchestrator to Teams and Microsoft 365 Copilot

`scripts/publish-m365.ps1` does the REST flow from Microsoft's "Publish agents to Microsoft 365 and Teams by using
the REST API" ([learn.microsoft.com](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot-virtual-network),
consulted 2026-11-03) for the hosted orchestrator ([ORCHESTRATOR.md](ORCHESTRATOR.md)). It is PowerShell 7, re-runnable,
supports `-WhatIf`, and holds no secret: every call goes through `az rest`, which obtains its own tokens.

Nothing here has been run against a live subscription. The tests drive the script against a fake `az`
(`backend/tests/test_publish_m365.py`) and the saved transcript ([evidence/publish-whatif.txt](evidence/publish-whatif.txt))
is that same fake. Treat the first real run as the sandbox spike it is (Prompt 6).

## Before you run it

| You need | Why |
| --- | --- |
| The orchestrator deployed and **active** as a hosted agent | The script reads its identity (`instance_identity.client_id`) from the project |
| **Foundry User** on the Foundry project | Create, manage and publish agents. (Deploying the agent needs **Foundry Project Manager**.) These roles were renamed from "Azure AI User / Project Manager"; the role ids are unchanged |
| **Azure Bot Service Contributor** (or Contributor/Owner) on the resource group | The script creates the Bot Service resource and its Teams channel there |
| `Microsoft.BotService` **registered** in the subscription | The script checks and, if not, prints `az provider register --namespace Microsoft.BotService` and stops. It never registers a provider; that is a subscription-wide change for the owner |
| Azure CLI 2.80+, signed in (`az login`) to the subscription | Everything goes through `az` |
| A client that can reach the project's **private endpoint**, if public network access is off | The agent calls (steps 1, 3, 4 and the download) stay private. Run from a VM in a connected network, or over VPN/ExpressRoute |

## Run it

```pwsh
# See what it would do. Reads the agent; creates, changes and publishes nothing.
pwsh scripts/publish-m365.ps1 -WhatIf `
  -ProjectEndpoint https://<account>.services.ai.azure.com/api/projects/<project> `
  -AgentName tcc-channel-orchestrator -ResourceGroup <rg> -BotName <bot> `
  -DisplayName "Tax Credit Copilot" `
  -ShortDescription "Questions about job-creation tax credits." `
  -FullDescription "Answers from the platform's own calculations, with the figures it computed."

# Then for real (scope Shared: just you, no admin approval).
pwsh scripts/publish-m365.ps1 <the same arguments, without -WhatIf>
```

| Parameter | Default | |
| --- | --- | --- |
| `-PublishScope` | `Shared` | `Shared` or `Tenant` (below) |
| `-ConfirmTenantPublish` | off | Required with `Tenant` |
| `-EnablePrivateNetworkRoute` | `$true` | `-EnablePrivateNetworkRoute:$false` for a project with public network access (the colon form is needed under `pwsh -File`) |
| `-AppVersion` | `1.0.0` | Semantic version. If it is already published the script tries the next patch version, repeatedly |
| `-OutputDir` | `./publish-output` | Where `appPackage.zip` and its extracted manifest are saved |
| `-SubscriptionId` | the current subscription | |
| `-DeveloperName`, `-DeveloperWebsiteUrl`, `-PrivacyUrl`, `-TermsOfUseUrl` | placeholders pointing at this repository's `SECURITY.md` and `DISCLAIMER.md` | Shown to users. HTTPS only. No secrets, no customer names |

## What it does

| # | Step | Request | Notes |
| --- | --- | --- | --- |
| 1 | Read the agent and the tenant | `GET {project}/agents/{name}` ; `az account show` | The agent's identity client id becomes the bot's app id |
| 2 | Bot Service | ARM `PUT .../botServices/{bot}?api-version=2022-09-15` then `.../channels/MsTeamsChannel?api-version=2021-03-01` | Single tenant (`msaAppType=SingleTenant`), `publicNetworkAccess=Disabled`, endpoint = the agent's `.../endpoint/protocols/activityProtocol?api-version=v1`. No Bicep |
| 3 | Endpoint settings (with `-EnablePrivateNetworkRoute`) | `PATCH {project}/agents/{name}` as `application/merge-patch+json` | See below |
| 4 | Publish | `POST {project}/agents/{name}/microsoft365/publish` | Success is declared **only** if a `titleId` comes back |
| 5 | Package | `POST .../microsoft365/zip` with the same body | Saved, extracted, and its manifest summarised. Needs agent write permission |

**The PATCH replaces `protocol_configuration` and `authorization_schemes`**, so the script reads the endpoint first,
merges, and sends everything it already had: every existing protocol, every existing scheme, any existing `activity`
setting. It adds `activity.enable_m365_public_endpoint = true` (the source-IP-filtered public route for the Activity
Protocol only; Responses and the management APIs stay private) and the Bot Service scheme for the scope, and swaps
out only the *other* Bot Service scheme. An endpoint with nothing configured gets `responses` and `activity`. Publishing
sets the scheme again and replaces a different Bot Service scheme, which is why the script sets the matching one up front.

## Scopes: who can find the agent, who can call it

| Scope | Scheme | Visible to | Admin approval |
| --- | --- | --- | --- |
| `Shared` (default) | `BotServiceRbac` | You, under **Your agents**; you share a link | No. If you add the agent to a Teams chat, participants who hold the required Foundry permissions on the project can use it |
| `Tenant` | `BotServiceTenant` | Everyone in the tenant, under **Built by your org** | **Yes**, in the Microsoft 365 admin center (<https://admin.cloud.microsoft/?#/agents/all/requested>) |

`-PublishScope Tenant` without `-ConfirmTenantPublish` stops before any request. With it, the script says an admin
must approve the submission. The orchestrator also has its own gate: a person who cannot write (the gateway's writer
check) cannot commit a change however the agent was published, and every call is audited under them.

## After publishing

1. Open Teams or Microsoft 365 Copilot, find the agent under **Your agents**, and share its link.
2. Check identity first. With `CHANNEL_DEBUG_WHOAMI=true` on the agent, send `/whoami`: it prints the identity signals the
   platform sent and what the orchestrator resolved. If it cannot name you, the agent answers that it can't tell who you
   are and runs nothing. That is the finding to bring back (spike S3).
3. Ask `Who should we call first?`, then a client question. Every figure is the engine's; each reply shows which method it
   used, the provenance footer, and the disclaimer.

## Updating a published agent

- **New agent code or model settings:** deploy a new hosted-agent version, then make it the active one. The published
  endpoint is stable; it receives traffic according to `agent_endpoint.version_selector`
  (`FixedRatio` rules: `agent_version`, `traffic_percentage: 100`). No republish is needed.
- **Name, descriptions, developer links:** re-run the script. A published `appVersion` cannot be republished, so each run
  that reaches the publish step moves to the next free patch version. The bot, channel and endpoint steps are idempotent.
- **Scope change:** re-run with the other scope (and `-ConfirmTenantPublish` for `Tenant`). The scheme is swapped.

## Removing a publish

The REST reference the script follows has no unpublish call, so the script does not remove anything. To take an agent
down: remove it from the Microsoft 365 admin center (Tenant scope) or from Teams **Your agents** (Shared), then delete the
Bot Service resource (`az bot delete -g <rg> -n <bot>`), which stops channel delivery. Removing `BotServiceRbac` /
`BotServiceTenant` from the agent endpoint (a merge-patch like step 3, keeping the other entries) closes the route.

## Limits that come with a published agent

No streaming and no citations. File uploads do not work in Microsoft 365 Copilot (they do in Teams); the claim package is
therefore a link from the gateway, not an attachment. Messages reach the container over the Responses protocol after the
platform converts the Activity protocol, so the sender's display name may not arrive (the audit row then says
`(name not provided)`; the object id is still recorded). Data in published agents is processed and stored by Microsoft 365
and Teams under their terms: review data residency and governance before publishing.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `Microsoft.BotService ... not registered` | A subscription owner runs the printed `az provider register` command, then re-run |
| `has no instance_identity.client_id` | The agent is not deployed or not active; check the version status |
| `Could not read agent` / 403 | The caller lacks **Foundry User**, or cannot reach the project's private endpoint |
| `Publish failed: ... already exists` repeated 50 times | The version space is exhausted; pass a higher `-AppVersion` |
| `did not return a titleId` | The service accepted but did not publish. Nothing is reported as published; read the response the script prints |
| Download fails with 403 | The zip call needs agent **write** permission, not just read |
| The agent replies "I can't tell who you are" | No identity signal carried an Entra object id: run `/whoami`, then set `CHANNEL_IDENTITY_SOURCES` (see ORCHESTRATOR.md) |
| Tenant publish is not visible | It is waiting for admin approval in the Microsoft 365 admin center |

## Tests

```pwsh
cd backend; ..\.venv\Scripts\python.exe -m pytest tests/test_publish_m365.py -q    # needs pwsh 7; skipped without it
python tests/make_publish_whatif.py                                                  # regenerate the saved transcript
```

They assert the request sequence and every payload (the bot, the channel, the merged PATCH including a case where
existing protocols and unknown schemes must survive, the publish body and the scope-to-scheme mapping), the tenant
guard (no request at all without `-ConfirmTenantPublish`), the provider check (prints the command, calls nothing else),
the version bump, "no `titleId` is not success", `-WhatIf` (reads, never writes), and that no token appears in any call.
