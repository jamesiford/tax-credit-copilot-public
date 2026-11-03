# Operating the sandbox PoC

Customer-neutral. How to see what is running, pause it, bring it back and take it down. Values
shown as `<...>` come from the azd environment (`azd env get-values`) or the private deploy notes.

## What runs, and what it costs to leave it

| Driver | Idle cost | Notes |
| --- | --- | --- |
| App Service plan (`asp-tcc-<s>`, default `P1v3`) | **Yes, hourly while it exists** | Carries four apps: web, API, channel gateway and, in the PoC, the mock model gateway. Stopping apps does not stop the plan's charge; scaling the plan down does |
| Foundry model deployment (`gpt-4.1-mini`, `GlobalStandard`) | No idle charge | Pay per token |
| Foundry hosted orchestrator | Check the hosted-agent pricing page for the region | Delete the agent version to stop any hosted-compute charge |
| Azure Bot Service | Free tier | Created by `scripts/publish-m365.ps1`, not by Terraform |
| Application Insights / Log Analytics | Per GB ingested | A smoke test is small |
| Storage (ZRS, two containers) | Pennies | |
| Private endpoints (blob, Foundry, and web when private) | **Yes, hourly each** | Part of the public profile's network |
| Fabric capacity | **Owner-managed** | The PoC reuses a capacity shared with other workspaces. It is not created, assigned or paused by anything here |

No price is stated here; run the SKUs through the Azure pricing calculator for the region.

## Pause and resume

```pwsh
pwsh scripts/poc-pause.ps1 -ResourceGroup <resource-group>            # stop the apps, plan to B1
pwsh scripts/poc-pause.ps1 -ResourceGroup <resource-group> -Resume    # plan back to its tag, apps started
```

The plan's original SKU is kept in the plan's `pause-sku` tag. `-WhatIf` shows the steps. The script
never touches the Fabric capacity; it prints the suspend command for the owner. A paused PoC answers
nothing: the web app, API, gateway and mock are all stopped, and a published agent will say the
platform did not answer. Allow a few minutes after resuming (the API's `/api/ready` can take up to ten
minutes on a cold start).

## Check it is healthy

```pwsh
$web = '<WEB_BASE_URL>'; $gw = '<CHANNEL_BASE_URL>'
Invoke-WebRequest "$web/healthz" -SkipHttpErrorCheck | Select-Object StatusCode      # 200 or 302 to sign-in
Invoke-WebRequest "$gw/channel/health"                                              # 200
Invoke-WebRequest "$gw/channel/v1/tools" -SkipHttpErrorCheck | Select-Object StatusCode   # 401: no token
python scripts/apply-migrations.py --target deployed                                # 0 pending
```

Failure signatures are in [RUNBOOK](../architecture/RUNBOOK.md). Two PoC-specific ones:

* Every data path fails while `/api/health` stays 200: the shared Fabric capacity is paused or
  the workspace was moved. Ask the owner; do not resume or assign a capacity from here.
* The gateway answers 502 `api_unavailable`: the gateway identity lost its `TCC.Agent` role, or the
  API is stopped. `pwsh scripts/assign-channel-roles.ps1 ...` is idempotent and prints what is missing.

## Take it down

> [!CAUTION]
> Teardown deletes the resource group, which holds everything Terraform created **and** the Bot
> Service resource and any hosted-agent resources made by the publish scripts. It does not touch the
> existing Fabric workspace, lakehouse or warehouse, and it does not remove tenant-level objects.

```pwsh
azd down --purge --force --no-prompt
az group exists --name <resource-group>        # expect false
```

Then, by hand, what Terraform cannot know about:

1. **Foundry soft-delete.** `--purge` and the destroy-time action purge the account; confirm with
   `az cognitiveservices account list-deleted`. A deleted account otherwise holds its subdomain for 48 hours.
2. **Teams / Copilot.** Remove the agent from Teams *Your agents* (Shared scope) or the Microsoft 365 admin
   centre. There is no unpublish call (see [PUBLISHING](PUBLISHING.md)).
3. **Entra.** Remove the Web registration's redirect URI and its `tcc-poc-web-mi` federated credential;
   delete the app-role assignments of the gateway identity and the agent identity (they disappear with
   the identities, but a stale assignment can linger in the portal).
4. **Fabric.** Remove the two workspace role assignments Terraform and the operator made for this
   deployment's identities (`id-tcc-api-<s>` and `id-tcc-channel-<s>`) if they were not removed with the
   service principals. Leave every other principal alone.
5. **Writers.** Remove the operator from `tcc_ops.channel_user` with `python scripts/channel-writers.py remove <oid>`
   before teardown if the warehouse is kept: the audit rows stay, the entitlement should not.
6. **Local.** `azd env delete tcc-poc-channel`, and delete `overlays/m365-poc/` and `infra/m365-poc.auto.tfvars`.

Observed teardown time is roughly 6 to 12 minutes.

## Turning the demo posture off

The PoC runs the Foundry data plane public to one operator address
(`TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS=true`, `TCC_FOUNDRY_ALLOWED_IP_RANGES=<operator>/32`) and the
gateway public (callers are authenticated by token). To close the Foundry side:

```pwsh
azd env set TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS false
azd env set TCC_FOUNDRY_ALLOWED_IP_RANGES ""
azd provision --no-prompt
```

After that the operator's workstation can no longer deploy or publish agents; see
[HARDENING-PLAN](../architecture/HARDENING-PLAN.md) for the real fix.
