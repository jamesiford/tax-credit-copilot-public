<#
.SYNOPSIS
  Runs the .NET queue worker locally, with the same settings as run-local.ps1.

.DESCRIPTION
  The API only QUEUES runs (the Run button, batches, base-year recalculation). TaxCredit.Worker is the process that executes them. Without it a run
  stays "queued" forever. Run it beside the API, in a second terminal. Both must use the same operational store: with the default sqlite persistence
  that is dotnet\artifacts\local\operations.db, shared automatically.

.EXAMPLE
  .\dotnet\run-worker.ps1                 # keeps polling the queue until Ctrl+C
  .\dotnet\run-worker.ps1 -Once           # drains what is queued now, then exits
  .\dotnet\run-worker.ps1 -Offline        # synthetic seed data, to match run-local.ps1 -Offline
#>
param(
    [ValidateSet('sqlite', 'warehouse')][string]$Persistence = 'sqlite',
    [switch]$Offline,
    [switch]$Once,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-env.ps1')

$mode = if ($Offline) { 'offline' } else { 'live' }
$settings = Get-TaxCreditLocalEnvironment -Mode $mode -Persistence $Persistence
if (-not $Offline -and -not (az account show --query user.name -o tsv 2>$null)) { throw 'Not signed in. Run: az login' }
foreach ($key in $settings.Keys) { Set-Item -Path "Env:$key" -Value $settings[$key] }

Set-Location $PSScriptRoot
$run = @('run', '--project', 'src\TaxCredit.Worker', '--no-launch-profile')
if ($NoBuild) { $run += '--no-build' }
if ($Once) { $run += @('--', '--once') }
Write-Host ($(if ($Once) { 'Draining the queue once' } else { 'Worker polling the queue (Ctrl+C to stop)' })) -ForegroundColor Green
& dotnet @run
