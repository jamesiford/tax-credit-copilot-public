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

.PARAMETER WhatIf
    Print what would be deployed and change nothing (nothing is built or uploaded).
#>
[CmdletBinding(SupportsShouldProcess)]
param()

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
    if ($LASTEXITCODE -ne 0) { throw "az webapp deploy failed with exit code $LASTEXITCODE" }
}

function Invoke-ChannelDeploy {
    if (-not (Test-ChannelEnabled)) {
        Write-Host 'channel gateway: not enabled (TCC_ENABLE_M365_CHANNEL is not true); nothing to deploy.'
        return
    }
    $appName = Get-RequiredSetting 'CHANNEL_APP_NAME'
    $resourceGroup = Get-RequiredSetting 'AZURE_RESOURCE_GROUP'
    if (-not $PSCmdlet.ShouldProcess("$appName in $resourceGroup", 'zip-deploy the channel gateway (backend/ with startup-channel.sh)')) {
        return
    }
    $package = Join-Path ([IO.Path]::GetTempPath()) ("tcc-channel-{0}.zip" -f [Guid]::NewGuid().ToString('N'))
    try {
        Write-Host "==> packaging backend/ for the channel gateway" -ForegroundColor Cyan
        New-ChannelPackage $package
        Write-Host "==> deploying to $appName" -ForegroundColor Cyan
        Publish-ChannelPackage $resourceGroup $appName $package
        Write-Host 'channel gateway deployed.' -ForegroundColor Green
    } finally {
        Remove-Item -LiteralPath $package -Force -ErrorAction SilentlyContinue
    }
}

Invoke-ChannelDeploy
