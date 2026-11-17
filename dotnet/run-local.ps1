<#
.SYNOPSIS
  Runs the .NET API locally against the live Fabric lakehouse, with local operational storage.

.DESCRIPTION
  Reads backend\.env (the settings the Python product already uses), maps them to the .NET names, and starts
  TaxCredit.Api on the port the Vite dev proxy expects (8000). Nothing is written to Fabric: operational state
  (claims, findings, runs) stays in a local SQLite file and artifacts stay on local disk unless you opt in.
  To run from Visual Studio instead, use configure-local.ps1.

  Prerequisites: `az login` as an identity that can read the lakehouse SQL endpoint, an ACTIVE Fabric capacity,
  and the .NET SDK selected by dotnet\global.json.

.EXAMPLE
  .\dotnet\run-local.ps1
  .\dotnet\run-local.ps1 -Port 8000 -Persistence sqlite
  .\dotnet\run-local.ps1 -Offline        # synthetic seed data only, no Azure calls
#>
param(
    [int]$Port = 8000,
    [ValidateSet('sqlite', 'warehouse')][string]$Persistence = 'sqlite',
    [switch]$Offline,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-env.ps1')

$mode = if ($Offline) { 'offline' } else { 'live' }
$settings = Get-TaxCreditLocalEnvironment -Mode $mode -Persistence $Persistence

if ($Offline) {
    Write-Host 'Offline: synthetic seed data, local SQLite, no Azure calls.' -ForegroundColor Yellow
}
else {
    $account = az account show --query user.name -o tsv 2>$null
    if (-not $account) { throw 'Not signed in. Run: az login' }
    Write-Host "Azure identity: $account" -ForegroundColor Cyan
    if ($Persistence -eq 'warehouse') {
        Write-Host 'Warehouse persistence: claims, findings and runs WRITE to the Fabric Warehouse.' -ForegroundColor Yellow
    }
    Write-Host "Source: lakehouse SQL endpoint (schema '$($settings['SOURCE_SCHEMA'])'), read-only. Operational store: $Persistence." -ForegroundColor Cyan
}
foreach ($key in $settings.Keys) { Set-Item -Path "Env:$key" -Value $settings[$key] }

# The AI providers stay disabled unless you set FOUNDRY_PROJECT_ENDPOINT yourself; see dotnet\README.md.
Set-Location $PSScriptRoot
$run = @('run', '--project', 'src\TaxCredit.Api', '--no-launch-profile')
if ($NoBuild) { $run += '--no-build' }
$run += @('--', '--urls', "http://127.0.0.1:$Port")
Write-Host "Starting http://127.0.0.1:$Port  (Ctrl+C to stop)" -ForegroundColor Green
& dotnet @run
