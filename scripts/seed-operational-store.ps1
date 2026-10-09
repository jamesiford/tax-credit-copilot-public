<#
.SYNOPSIS
    Seed the operational store (tcc_ops in the Fabric Warehouse) after provisioning.

.DESCRIPTION
    A freshly bootstrapped Warehouse holds no claims or engagements. Without
    this the coverage matrix renders blank — every cell reads "unclaimed" —
    which looks like a broken portal rather than an unseeded one.

    Runs as an azd `postprovision` hook AFTER `apply-migrations.py` (D22), so
    `azd up` stays one command.

    Two things this deliberately does NOT do:

    - It does not create tables. The schema is DDL v2.0 plus migrations, applied
      by scripts/apply-migrations.py; schema in two places can disagree.
    - It does not invent claims. Every claim row it writes is `client_asserted`
      provenance — what a client told us at onboarding, never something we
      computed. `backend/data/seed_claims.py` carries the assertions and the
      reasoning.

    Idempotent: re-running writes nothing new. Seeding an assertion requires the
    cell to have been assessed first (an assertion is recorded *against* a
    computed figure), so on a first provision the assertions are reported and
    skipped; engagements are written once and then left alone.

.NOTES
    Authenticates with DefaultAzureCredential (the deploying user locally, OIDC
    in CI). The identity needs write access to tcc_ops: a Fabric workspace role
    plus the T-SQL grants, not Azure RBAC.
#>
[CmdletBinding()]
param(
    # Skip the write and just report what would change.
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

$server = $env:WAREHOUSE_SERVER
$database = $env:WAREHOUSE_DATABASE

if ([string]::IsNullOrWhiteSpace($server) -or [string]::IsNullOrWhiteSpace($database)) {
    Write-Host 'WAREHOUSE_SERVER / WAREHOUSE_DATABASE are not set; skipping the operational-store seed.' -ForegroundColor Yellow
    Write-Host 'This is expected if the environment has not been provisioned yet.'
    exit 0
}

Write-Host "Seeding operational store at $server (database: $database)" -ForegroundColor Cyan

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPython) { $venvPython } else { 'python' }

Push-Location (Join-Path $repoRoot 'backend')
try {
    $env:CLAIM_STORE = 'warehouse'
    $env:FINDING_STORE = 'warehouse'

    if ($WhatIf) {
        Write-Host 'WhatIf: would run `python -m data.seed_claims` against the Warehouse.' -ForegroundColor Yellow
        exit 0
    }

    & $python -m data.seed_claims
    if ($LASTEXITCODE -ne 0) {
        throw "seed_claims exited with $LASTEXITCODE"
    }
    Write-Host 'Operational store seeded.' -ForegroundColor Green
}
finally {
    Pop-Location
}
