<#
.SYNOPSIS
  Runs the .NET API locally against the same data sources as a deployed host: the Fabric lakehouse (payroll) and the Warehouse or Azure SQL (results).

.DESCRIPTION
  Reads backend\.env (the settings the Python product already uses), maps them to the .NET names, and starts
  TaxCredit.Api on the port the Vite dev proxy expects (8000). Claims, findings, runs and batches are written to the Warehouse
  (WAREHOUSE_SERVER / WAREHOUSE_DATABASE); the payroll is read from the lakehouse. Artifacts go to Blob if ARTIFACT_BLOB_ACCOUNT_URL is set,
  otherwise to local disk. -Offline is the one exception: synthetic data, local SQLite, no Azure.
  To run from Visual Studio instead, use configure-local.ps1.

  Prerequisites: `az login` as an identity that can read the lakehouse SQL endpoint, an ACTIVE Fabric capacity,
  and the .NET SDK selected by dotnet\global.json.

.EXAMPLE
  .\dotnet\run-local.ps1
  .\dotnet\run-local.ps1 -Port 8000
  .\dotnet\run-local.ps1 -Offline        # synthetic seed data only, no Azure calls
#>
param(
    [int]$Port = 8000,
    [switch]$Offline,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-env.ps1')

$mode = if ($Offline) { 'offline' } else { 'live' }
$settings = Get-TaxCreditLocalEnvironment -Mode $mode

if ($Offline) {
    Write-Host 'Offline: synthetic seed data, local SQLite, no Azure calls.' -ForegroundColor Yellow
}
else {
    $account = az account show --query user.name -o tsv 2>$null
    if (-not $account) { throw 'Not signed in. Run: az login' }
    Write-Host "Azure identity: $account" -ForegroundColor Cyan
    Write-Host 'Claims, findings and runs WRITE to the Warehouse database named in backend\.env.' -ForegroundColor Yellow
    Write-Host "Source: lakehouse SQL endpoint (schema '$($settings['SOURCE_SCHEMA'])'), read-only. Operational store: Warehouse." -ForegroundColor Cyan
}
foreach ($key in $settings.Keys) { Set-Item -Path "Env:$key" -Value $settings[$key] }

# The AI providers stay disabled unless you set FOUNDRY_PROJECT_ENDPOINT yourself; see dotnet\README.md.
Set-Location $PSScriptRoot
$run = @('run', '--project', 'src\TaxCredit.Api', '--no-launch-profile')
if ($NoBuild) { $run += '--no-build' }
$run += @('--', '--urls', "http://127.0.0.1:$Port")
Write-Host "Starting http://127.0.0.1:$Port  (Ctrl+C to stop)" -ForegroundColor Green
& dotnet @run
