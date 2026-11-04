<#
.SYNOPSIS
    Zip-deploy the Microsoft 365 channel gateway, only when the channel is enabled. [CH-07b]

.DESCRIPTION
    azd cannot make a service conditional: it resolves every service in azure.yaml
    by its `azd-service-name` tag, and with `enable_m365_channel = false` there is
    no gateway app, so a `channel` service would break `azd up` for every default
    deployment. The gateway is therefore deployed from a `postdeploy` hook (and
    from deploy.yml) by this script instead.

    With TCC_ENABLE_M365_CHANNEL not `true` this exits 0 at once and says so in one
    quiet line. With it on, it builds the same package the `api` service uses
    (scripts/package-app.py over backend/, which carries `channel/` and
    `startup-channel.sh`) and zip-deploys it to the app Terraform named in the
    CHANNEL_APP_NAME output. Re-running deploys the same code again: idempotent.

    Inputs come from the azd environment (azd exports it to hooks):
      TCC_ENABLE_M365_CHANNEL  `true` to deploy
      CHANNEL_APP_NAME         the gateway app (Terraform output)
      AZURE_RESOURCE_GROUP     its resource group (Terraform output)
      CHANNEL_BASE_URL         its https address (Terraform output); the default hostname when unset
      TCC_CHANNEL_HEALTH_CHECK `off` to skip the health wait below (a workstation that cannot reach it)

    `az webapp deploy` has been seen to report that the site did not start within ten minutes for a gateway that was
    serving and ready minutes earlier (its first build is slow). So the deploy's own verdict is not the verdict: after
    it, `GET /channel/health` is retried, bounded, and the hook succeeds when that answers 200 and fails, saying what
    it saw, when it never does. [CH-14]

.PARAMETER WhatIf
    Print what would be deployed and change nothing (nothing is built or uploaded).

.PARAMETER NoRun
    Define the functions and stop: the tests dot-source the script and replace the probe and the clock.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$NoRun,
    [int]$HealthTimeoutSeconds = 600,
    [int]$HealthIntervalSeconds = 10
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Test-ChannelEnabled {
    return ([Environment]::GetEnvironmentVariable('TCC_ENABLE_M365_CHANNEL') -eq 'true')
}

function Get-RequiredSetting([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq 'null') {
        throw "$Name is not set in the azd environment. The channel is enabled, so Terraform should have output it; did 'azd provision' complete?"
    }
    return $value
}

function Get-PythonPath {
    $venv = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (Test-Path $venv) { return $venv }
    if (Get-Command python3 -ErrorAction SilentlyContinue) { return 'python3' }
    return 'python'
}

function New-ChannelPackage([string]$Destination) {
    & (Get-PythonPath) (Join-Path $PSScriptRoot 'package-app.py') (Join-Path $repoRoot 'backend') $Destination
    if ($LASTEXITCODE -ne 0) { throw "packaging failed with exit code $LASTEXITCODE" }
}

function Publish-ChannelPackage([string]$ResourceGroup, [string]$AppName, [string]$Package) {
    & az webapp deploy -g $ResourceGroup -n $AppName --src-path $Package --type zip --async false
    return $LASTEXITCODE
}

function Get-HealthStatus([string]$Url) {
    try {
        return [int](Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 20 -SkipHttpErrorCheck).StatusCode
    } catch {
        return 0
    }
}

function Get-Now { return [DateTime]::UtcNow }

function Wait-Seconds([int]$Seconds) { Start-Sleep -Seconds $Seconds }

# Bounded: it returns the last status it saw, 200 as soon as the gateway answers, never loops forever.
function Wait-ChannelHealthy([string]$BaseUrl) {
    $url = "$($BaseUrl.TrimEnd('/'))/channel/health"
    $deadline = (Get-Now).AddSeconds($HealthTimeoutSeconds)
    $last = 0
    while ($true) {
        $last = Get-HealthStatus $url
        if ($last -eq 200 -or (Get-Now) -ge $deadline) { return $last }
        Wait-Seconds $HealthIntervalSeconds
    }
}

function Invoke-ChannelDeploy {
    if (-not (Test-ChannelEnabled)) {
        Write-Host 'channel gateway: not enabled (TCC_ENABLE_M365_CHANNEL is not true); nothing to deploy.'
        return
    }
    $appName = Get-RequiredSetting 'CHANNEL_APP_NAME'
    $resourceGroup = Get-RequiredSetting 'AZURE_RESOURCE_GROUP'
    if ($PSCmdlet -and -not $PSCmdlet.ShouldProcess("$appName in $resourceGroup", 'zip-deploy the channel gateway (backend/ with startup-channel.sh)')) {
        return
    }
    $package = Join-Path ([IO.Path]::GetTempPath()) ("tcc-channel-{0}.zip" -f [Guid]::NewGuid().ToString('N'))
    try {
        Write-Host "==> packaging backend/ for the channel gateway" -ForegroundColor Cyan
        New-ChannelPackage $package
        Write-Host "==> deploying to $appName" -ForegroundColor Cyan
        $deployExit = Publish-ChannelPackage $resourceGroup $appName $package
        if ([Environment]::GetEnvironmentVariable('TCC_CHANNEL_HEALTH_CHECK') -eq 'off') {
            if ($deployExit -ne 0) { throw "az webapp deploy failed with exit code $deployExit" }
            Write-Host 'channel gateway deployed (health check skipped).' -ForegroundColor Green
            return
        }
        $baseUrl = [Environment]::GetEnvironmentVariable('CHANNEL_BASE_URL')
        if ([string]::IsNullOrWhiteSpace($baseUrl) -or $baseUrl -eq 'null') { $baseUrl = "https://$appName.azurewebsites.net" }
        Write-Host "==> waiting for $baseUrl/channel/health" -ForegroundColor Cyan
        $status = Wait-ChannelHealthy $baseUrl
        if ($status -ne 200) {
            throw "channel gateway is not healthy: GET /channel/health answered $status after up to $HealthTimeoutSeconds s (az webapp deploy exit code $deployExit)."
        }
        if ($deployExit -ne 0) {
            Write-Host "az webapp deploy reported exit code $deployExit, but the gateway answers /channel/health with 200: treating the deployment as successful." -ForegroundColor Yellow
        }
        Write-Host 'channel gateway deployed and healthy.' -ForegroundColor Green
    } finally {
        Remove-Item -LiteralPath $package -Force -ErrorAction SilentlyContinue
    }
}

if (-not $NoRun) { Invoke-ChannelDeploy }
