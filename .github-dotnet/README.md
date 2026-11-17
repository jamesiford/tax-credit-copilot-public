# Dormant .NET workflow templates

GitHub **does not execute `.github-dotnet`**. Activation is an owner-reviewed
copy of selected `dotnet-*.yml` files to `.github/workflows/` after integration;
this delivery does not perform that copy or alter existing Python workflows.
All `uses` and `run` paths assume a checkout at repository root, not this folder.
Only explicitly marked build/format/test steps change directory to `dotnet`;
deployment scripts resolve their own repository/resource roots.

`dotnet-ci.yml` pins SDK **10.0.404** and CPython **3.12**, keeps API and gateway
replay in separate jobs, and calls the existing semantic policy unchanged.
**Expected inherited failure:** framework waiver share exceeds 25%; the template
does not convert a completed replay into parity success. Raw replay, logs, token
material, configuration, SQL data and package contents are never uploaded.
Only allowlisted aggregate reports are retained for seven days. The source-image
job uses a fresh locked restore; product source/central packages are unchanged.
`dotnet-heavy.yml` schedules the existing heavy suite separately and requests
no live-service approval. A fast run is not described as that suite.

`dotnet-deploy.yml` is manual, application-only and unavailable until both the
native-prerequisite input and protected `DOTNET_RELEASE_APPROVAL=approved` are
present. Configure the `dotnet-preproduction` environment with reviewer/branch
protection, a VNet-reachable Linux runner labelled `tcc-dotnet-vnet`, and a separate
OIDC **publisher** identity allowed to deploy only the independent .NET targets.
The runtime API/gateway identities are not publishing identities. Environment
variables named in the file are operator-owned non-secret references; never put
real values in this template. Pin `GIT_COMMIT` on the pre-provisioned target to
the release revision in the separate approved configuration operation first.

The guard checks subscription, exact distinct names/ARM identity, ownership and
azd tags, private networking, user-assigned identity, .NET 10 DLL startup and
runtime revision before deploying a verified zip. It does not create resources,
change app settings, initialize Terraform state, grant permissions or invoke
Python postprovision. Worker and orchestrator cannot be selected. A successful
deployment operation is not native data readiness, semantic parity or proof of
the served revision; follow `dotnet/deploy/HYBRID-OPS.md` to verify those.

Run actionlint against the files explicitly:

```powershell
actionlint -config-file .github-dotnet/actionlint.yaml .github-dotnet/dotnet-ci.yml .github-dotnet/dotnet-heavy.yml .github-dotnet/dotnet-deploy.yml
```

Default discovery audits `.github/workflows` and would miss these templates.
The explicit config declares the real private-runner label, not a lint waiver.
Activation may copy it to `.github/actionlint.yaml` or retain the explicit flag.
Workflow execution/OIDC/private SCM has not been exercised locally.
