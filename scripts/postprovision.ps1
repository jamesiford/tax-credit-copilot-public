<#
.SYNOPSIS
    azd postprovision: schema, data, grants and seed, in that order. [D22, DATA-8, FAB-3, TF-4]

.DESCRIPTION
    Runs after every `azd provision` / `azd up`, reading Terraform outputs from
    the azd environment:

      1. apply-migrations    `--bootstrap` ONLY when TCC_FABRIC_CREATED=true,
                             i.e. Terraform created this Warehouse. The script
                             still refuses the bootstrap if the Warehouse
                             already has tcc_ops.schema_migration, so a re-run
                             applies nothing.
      2. load-synthetic      public profile only: the synthetic source dataset
                             into the new Lakehouse (data.source.load_fabric).
      3. grant-warehouse-sql T-SQL grants on tcc_gold / tcc_ops to the API identity.
      4. seed-operational-store  idempotent.

    Every SQL step addresses the target `deployed`, which the guard resolves
    through the Fabric API and checks against FABRIC_WORKSPACE_ID /
    FABRIC_WAREHOUSE_ID / WAREHOUSE_SERVER before executing anything.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPython) { $venvPython } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }

# azd exports the environment's values to hooks; make sure the outputs are there.
foreach ($name in 'WAREHOUSE_SERVER', 'WAREHOUSE_DATABASE', 'FABRIC_WORKSPACE_ID', 'FABRIC_WAREHOUSE_ID') {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "$name is not set in the azd environment; did terraform apply complete?"
    }
}

function Invoke-Step([string]$Title, [scriptblock]$Body) {
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0) { throw "$Title failed with exit code $LASTEXITCODE" }
}

$created = ($env:TCC_FABRIC_CREATED -eq 'true')
Invoke-Step 'apply-migrations' {
    if ($created) {
        & $python (Join-Path $PSScriptRoot 'apply-migrations.py') --target deployed --bootstrap
    } else {
        & $python (Join-Path $PSScriptRoot 'apply-migrations.py') --target deployed
    }
}

if ($env:TCC_PROFILE -eq 'public') {
    Invoke-Step 'load-synthetic' {
        Push-Location (Join-Path $repoRoot 'backend')
        try {
            & $python -m data.source.load_fabric --synthetic-only --schema $(if ($env:SOURCE_SCHEMA) { $env:SOURCE_SCHEMA } else { 'tcc_source' })
        } finally { Pop-Location }
    }
}

Invoke-Step 'grant-warehouse-sql' {
    & $python (Join-Path $PSScriptRoot 'grant-warehouse-sql.py') --target deployed
}

Invoke-Step 'seed-operational-store' {
    & (Join-Path $PSScriptRoot 'seed-operational-store.ps1')
}

Write-Host 'postprovision complete.' -ForegroundColor Green
