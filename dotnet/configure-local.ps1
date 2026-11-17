<#
.SYNOPSIS
  Prepares the environment for running the .NET API locally without starting it.

.DESCRIPTION
  Writes a Visual Studio launch profile for TaxCredit.Api (src\TaxCredit.Api\Properties\launchSettings.json, which is
  gitignored because it holds your lakehouse host name) and, with -Session, also sets the same variables in the current
  PowerShell session. Then pick the profile in Visual Studio and press Run, or use `dotnet run --launch-profile`.

  Profiles written:
    "TaxCredit.Api - live lakehouse"   reads the live lakehouse (backend\.env), local SQLite for operational state
    "TaxCredit.Api - offline"          synthetic seed data, no Azure calls

.EXAMPLE
  .\dotnet\configure-local.ps1                 # write the profiles
  .\dotnet\configure-local.ps1 -Session        # also export the live variables into this PowerShell session
  .\dotnet\configure-local.ps1 -Persistence warehouse   # live profile also writes claims/findings/runs to the Warehouse
#>
param(
    [int]$Port = 8000,
    [ValidateSet('sqlite', 'warehouse')][string]$Persistence = 'sqlite',
    [switch]$Session
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local-env.ps1')

$live = Get-TaxCreditLocalEnvironment -Mode live -Persistence $Persistence
$offline = Get-TaxCreditLocalEnvironment -Mode offline

function New-Profile($variables) {
    $merged = [ordered]@{ ASPNETCORE_ENVIRONMENT = 'Production' }
    foreach ($key in $variables.Keys) { $merged[$key] = $variables[$key] }
    [ordered]@{
        commandName          = 'Project'
        dotnetRunMessages    = $true
        launchBrowser        = $true
        launchUrl            = 'api/ready'
        applicationUrl       = "http://127.0.0.1:$Port"
        environmentVariables = $merged
    }
}

$launch = [ordered]@{
    profiles = [ordered]@{
        'TaxCredit.Api - live lakehouse' = New-Profile $live
        'TaxCredit.Api - offline'        = New-Profile $offline
    }
}

$target = Join-Path $PSScriptRoot 'src\TaxCredit.Api\Properties\launchSettings.json'
New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
$launch | ConvertTo-Json -Depth 6 | Set-Content $target -Encoding utf8
Write-Host "Wrote $target" -ForegroundColor Green
Write-Host "In Visual Studio: set TaxCredit.Api as the startup project, choose the profile next to the Run button, press Run." -ForegroundColor Cyan

if ($Persistence -eq 'warehouse') {
    Write-Host 'Warehouse persistence: claims, findings and runs WRITE to the Fabric Warehouse (unvalidated; needs tcc_ops.finding_audit).' -ForegroundColor Yellow
}

if ($Session) {
    foreach ($key in $live.Keys) { Set-Item -Path "Env:$key" -Value $live[$key] }
    Write-Host "Exported $($live.Count) variables into this PowerShell session." -ForegroundColor Green
}

if (-not (az account show --query user.name -o tsv 2>$null)) {
    Write-Host 'Reminder: you are not signed in to Azure. Run: az login' -ForegroundColor Yellow
}
