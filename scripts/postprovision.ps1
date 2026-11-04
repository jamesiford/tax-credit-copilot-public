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
      2. load-synthetic      public profile only, and only when Terraform created
                             this Lakehouse (TCC_FABRIC_CREATED=true): the synthetic
                             source dataset into the new Lakehouse
                             (data.source.load_fabric). `--synthetic-only` OVERWRITES
                             every table it writes, so it never runs against a
                             brought (existing) Lakehouse, whatever the profile.
      3. grant-warehouse-sql T-SQL grants on tcc_gold / tcc_ops to the API identity; when
                             the channel is enabled (GATEWAY_IDENTITY_NAME is set), also
                             INSERT/SELECT on tcc_ops.channel_audit to the gateway
                             identity, at object level only. When the governed data query's
                             lakehouse source is on (TCC_DATA_QUERY_SOURCE_ENABLED=true), also
                             READ-ONLY SELECT on the source payroll tables, on the lakehouse
                             SQL analytics endpoint, to the API identity (never the gateway).
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

if ($env:TCC_PROFILE -eq 'public' -and $created) {
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

# The channel gateway writes the audit trail and nothing else in the Warehouse:
# object-level INSERT and SELECT on tcc_ops.channel_audit, no schema grant. The
# output is empty unless Terraform ran with enable_m365_channel. GRANT is
# idempotent, so a re-run changes nothing.
if (-not [string]::IsNullOrWhiteSpace($env:GATEWAY_IDENTITY_NAME) -and $env:GATEWAY_IDENTITY_NAME -ne 'null') {
    Invoke-Step 'grant-warehouse-sql (channel gateway)' {
        & $python (Join-Path $PSScriptRoot 'grant-warehouse-sql.py') --target deployed --profile gateway --principal $env:GATEWAY_IDENTITY_NAME
    }
}

# The governed data query's lakehouse source reads the payroll tables through the lakehouse
# SQL analytics endpoint. The API identity gets object-level SELECT on exactly the tables
# the semantic model names; no write, no schema grant, and never the gateway identity.
# Off unless the azd value TCC_DATA_QUERY_SOURCE_ENABLED is true (the same value Terraform
# maps to DATA_QUERY_SOURCE_ENABLED). GRANT is idempotent.
if ($env:TCC_DATA_QUERY_SOURCE_ENABLED -eq 'true') {
    Invoke-Step 'grant-warehouse-sql (lakehouse endpoint, read-only)' {
        & $python (Join-Path $PSScriptRoot 'grant-warehouse-sql.py') --target deployed --profile lakehouse
    }
}

Invoke-Step 'seed-operational-store' {
    & (Join-Path $PSScriptRoot 'seed-operational-store.ps1')
}

Write-Host 'postprovision complete.' -ForegroundColor Green
