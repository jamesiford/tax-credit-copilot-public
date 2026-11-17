# Independent .NET deployment assets

**Runnable local assets, not production release approval.** Start with
[`DEPLOYMENT-MATRIX.md`](DEPLOYMENT-MATRIX.md),
[`CONFIGURATION.md`](CONFIGURATION.md) and
[`HYBRID-OPS.md`](HYBRID-OPS.md). Native schema/grants, W3 parity/privacy,
dependency readiness, Worker supervision and authenticated orchestrator ingress
remain explicit prerequisites. No cloud deployment was performed.

## Reproduce from a checkout

Run from the repository root in PowerShell, with Docker's Linux engine available:

```powershell
$python = 'C:\Projects\py312-oracle\.venv\Scripts\python.exe'
& $python dotnet\deploy\publish.py --service all
& $python dotnet\deploy\build_images.py
& $python dotnet\deploy\container_smoke.py
& $python dotnet\deploy\smoke.py
& $python -m unittest discover -s dotnet\deploy -p test_deployment.py -q
& $python -m unittest discover -s dotnet\deploy\configuration -p test_*.py -q
```

Scripts anchor paths to this tree, select SDK **10.0.404** from the staged
`global.json`, and publish framework-dependent **net10.0**. CPython **3.12**
is required by the publication CLI. `publish.ps1` provides the equivalent
PowerShell entry; `TCC_DEPLOY_PYTHON` selects its interpreter without putting an
operator-specific path in the azd manifest. Product projects, central packages
and Python deployment assets are never edited.

All four Dockerfiles are multi-stage, use digest-pinned .NET 10 images, and run
as `app`. The SDK stage runs on the builder's native CPU and cross-publishes
`linux-x64`; final images explicitly target **linux/amd64**, including Responses.
This matters on an arm64 engine: emulating the SDK build failed locally.
API/gateway resources are root-owned and smoke-tested with a read-only rootfs.
Worker has no invented port or HTTP health check.

Local container NuGet HTTPS failed with `NU1301` / OpenSSL handshake failure.
No certificate verification was disabled. The measured source-build alternative:

```powershell
& $python dotnet\deploy\build_images.py --offline-feed
```

This copies **only exact locked public `.nupkg` archives**, not a user's NuGet
directory, config or credentials. Archive SHA-512/cache metadata are checked;
the fresh container locked restore remains the authoritative NuGet content-hash
check (signed-package content hashes differ from raw archive hashes).
The alternative disables the unavailable vulnerability-audit network call for
that offline build only. It is not a vulnerability assessment. Normal CI keeps
NuGet audit enabled. Existing source-package licenses/pins are unchanged; the
optional deployment hook is BCL-only.

## Artifact and packaging contract

Ordinary outputs: `.artifacts/publish/{api,worker,gateway,orchestrator}`.
The actual `TaxCredit.<Executable>.dll` is at package root, alongside its runtime
and dependency files. `artifact-manifest.json` contains service, full source
commit and per-file SHA-256, never configuration. Images carry
`org.opencontainers.image.revision` and `/app/checksums.sha256`; build evidence
records image IDs/architecture/nonroot status.

API/Worker/gateway retain `resources/backend/rules/**`, the exact ingested
JSON inputs, SQL schema/migrations and **both consumed public synthetic CSVs**.
Orchestrator receives none of that payroll/rule/schema tree. The embedded source
mapping and prompt `.resx` must also enter the *build* context; staging includes
them explicitly. No private extract, `.env`, operational database, token cache,
contract seed or blanket backend copy is staged. Only git-tracked product inputs
are selected. Deployment-owned hook source is separately bounded to its project.

`locks/<project>/packages.lock.json` freezes this existing product graph under
deployment ownership. `stage.py` copies these into the isolated project tree;
both publication and Docker builds use **locked restore**, without adding locks
to application projects. For an approved dependency change, regenerate locks
only in that staging tree with SDK 10.0.404 and `-r linux-x64`, review/copy the
resulting project locks back here, then repeat locked publication/source builds.
Never use `--force-evaluate` on the release build.

For code deployment:

```powershell
& $python dotnet\deploy\publish.py --service api --runtime linux-x64
& $python dotnet\deploy\package_zip.py --service api
```

The zip verifier rejects missing/unmanifested/tampered files and links.
Fixed entry timestamps/order make repeated zips of one publication deterministic;
this is not a promise of bit-identical apt/SDK rebuilds. Release promotion should
reuse a verified immutable artifact, not rebuild it under the same release name.

Every package/image includes the optional hook under `telemetry/`; it is
**disabled by default**, and Terraform does not activate it. To opt in, use
`DOTNET_STARTUP_HOOKS=/app/telemetry/TaxCredit.Deployment.Telemetry.dll`
(App Service: `/home/site/wwwroot/telemetry/...`) plus the exact safe settings in
[`telemetry/README.md`](telemetry/README.md). Never apply startup-hook settings
to SDK/build processes. The collector/backend is operator-owned.

## azd, deliberately independent

Always select this manifest explicitly with `azd -C dotnet\deploy ...`.
Its service names are `dotnet-api`, `dotnet-worker`, `dotnet-gateway`; they do not
reuse Python names/tags/state. Deployment-owned `.csproj` proxies invoke the same
publisher and protect product projects from azd's user-secrets initialization.
The MSBuild proxy was locally published and its actual DLL/resources/manifest
checked. No live azd environment or service deployment was initialized.

After separately approved native provisioning/configuration and release closure:

```powershell
azd -C dotnet\deploy package dotnet-api --no-prompt --output-path .artifacts\azd-api.zip
azd -C dotnet\deploy deploy dotnet-api --no-prompt
```

Use the gateway service name for a gateway-only operation. **Never use
unqualified/all-service `up` or `deploy`.** Worker packaging exists but has no
App Service resource and its deploy hook refuses. The root preprovision hook
always refuses automatic provisioning; there is no Python postprovision chain.
Orchestrator is intentionally not an azd service.

The deploy guard defaults off, requires explicit .NET target/revision variables
and activation, then checks live OIDC subscription, exact names/ARM identity,
private ingress, UAMI, ownership/azd tags, .NET stack/DLL and runtime `GIT_COMMIT`.
The operator must stage that matching runtime revision under the approved writer
pause; the application-only workflow deliberately does not change settings.
Those live checks were **not** run here; positive/negative metadata fixtures
exercise the guard without Azure. Provisioning is separately owned under
[`infra-dotnet`](../../infra-dotnet/README.md); see its validated input/output
contract and dedicated backend requirements.

`.github-dotnet` contains **dormant** installable workflows, not active GitHub CI.
Its README gives activation, private-runner/OIDC and safe-retention details.
