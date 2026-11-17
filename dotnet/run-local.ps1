<#
.SYNOPSIS
  Runs the .NET API locally against the live Fabric lakehouse, with local operational storage.

.DESCRIPTION
  Reads backend\.env (the settings the Python product already uses), maps them to the .NET names, and starts
  TaxCredit.Api on the port the Vite dev proxy expects (8000). Nothing is written to Fabric: operational state
  (claims, findings, runs) stays in a local SQLite file and artifacts stay on local disk unless you opt in.

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
$dotnet = $PSScriptRoot
$repo = Split-Path $dotnet -Parent
$envFile = Join-Path $repo 'backend\.env'

function Read-DotEnv([string]$path) {
    $map = @{}
    if (Test-Path $path) {
        Get-Content $path | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' } | ForEach-Object {
            $k, $v = $_ -split '=', 2
            $map[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
        }
    }
    return $map
}

if ($Offline) {
    $env:ENVIRONMENT = 'local'
    $env:AUTH_MODE = 'none'
    $env:DATA_SOURCE = 'csv'
    $env:TCC_PERSISTENCE_PROVIDER = 'sqlite'
    $env:ARTIFACT_STORE = 'local'
    Write-Host 'Offline: synthetic seed data, local SQLite, no Azure calls.' -ForegroundColor Yellow
}
else {
    $cfg = Read-DotEnv $envFile
    foreach ($required in 'LAKEHOUSE_SQL_SERVER', 'LAKEHOUSE_SQL_DATABASE') {
        if (-not $cfg[$required]) { throw "$required is missing from $envFile" }
    }
    $account = az account show --query user.name -o tsv 2>$null
    if (-not $account) { throw 'Not signed in. Run: az login' }
    Write-Host "Azure identity: $account" -ForegroundColor Cyan

    $env:ENVIRONMENT = 'local'
    $env:AUTH_MODE = if ($cfg['AUTH_MODE']) { $cfg['AUTH_MODE'] } else { 'none' }
    $env:DATA_SOURCE = 'lakehouse'
    $env:SOURCE_SQL_SERVER = $cfg['LAKEHOUSE_SQL_SERVER']
    $env:SOURCE_SQL_DATABASE = $cfg['LAKEHOUSE_SQL_DATABASE']
    if ($cfg['SOURCE_SCHEMA']) { $env:SOURCE_SCHEMA = $cfg['SOURCE_SCHEMA'] }
    $env:ARTIFACT_STORE = 'local'
    # DefaultAzureCredential would otherwise try Visual Studio / VS Code sign-ins first, which may be a different account.
    $env:AZURE_TOKEN_CREDENTIALS = 'AzureCliCredential'

    $env:TCC_PERSISTENCE_PROVIDER = $Persistence
    if ($Persistence -eq 'warehouse') {
        foreach ($required in 'WAREHOUSE_SERVER', 'WAREHOUSE_DATABASE') {
            if (-not $cfg[$required]) { throw "$required is missing from $envFile" }
        }
        $env:FABRIC_SQL_SERVER = $cfg['WAREHOUSE_SERVER']
        $env:FABRIC_SQL_DATABASE = $cfg['WAREHOUSE_DATABASE']
        Write-Host 'Warehouse persistence: claims, findings and runs WRITE to the Fabric Warehouse.' -ForegroundColor Yellow
    }
    Write-Host "Source: lakehouse SQL endpoint (schema '$($env:SOURCE_SCHEMA)'), read-only. Operational store: $Persistence." -ForegroundColor Cyan
}

# The AI providers stay disabled unless you set FOUNDRY_PROJECT_ENDPOINT yourself; see dotnet\README.md.
Set-Location $dotnet
$run = @('run', '--project', 'src\TaxCredit.Api', '--no-launch-profile')
if ($NoBuild) { $run += '--no-build' }
$run += @('--', '--urls', "http://127.0.0.1:$Port")
Write-Host "Starting http://127.0.0.1:$Port  (Ctrl+C to stop)" -ForegroundColor Green
& dotnet @run
