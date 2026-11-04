<#
.SYNOPSIS
    Publish a Foundry hosted agent to Microsoft 365 Copilot and Teams. [CH-09]

.DESCRIPTION
    The REST flow from "Publish agents to Microsoft 365 and Teams by using the REST API"
    (https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot-virtual-network,
    consulted 2026-11-03), as one idempotent, re-runnable script:

      1. read the agent (its identity client id and current endpoint settings) and the tenant;
      2. create or update the Azure Bot Service resource (single tenant, public network access
         disabled, endpoint = the agent's Activity Protocol route) and its Teams channel;
      3. with -EnablePrivateNetworkRoute, PATCH the agent endpoint to turn on the source-IP-filtered
         Activity Protocol route and the Bot Service authorization scheme for the scope. That PATCH
         REPLACES protocol_configuration and authorization_schemes, so the script reads the current
         values, merges, and sends everything the endpoint already had;
      4. publish (POST .../microsoft365/publish), raising the patch version when the version already
         exists, and report success only when a titleId comes back;
      5. download the validated app package and print its manifest summary.

    Everything goes through `az rest`, so `az` obtains every token itself and no token, key or other
    secret is ever read, held or printed by this script. There is no Bicep: the bot is one ARM PUT.
    The script never registers a resource provider; if Microsoft.BotService is not registered it prints
    the command and stops.

    Re-running is safe: the bot, the channel and the endpoint settings are idempotent. Each run that
    reaches step 4 publishes a NEW patch version (a published version cannot be republished).

.PARAMETER ProjectEndpoint
    https://<resource>.services.ai.azure.com/api/projects/<project>
.PARAMETER AgentName
    The hosted agent's name.
.PARAMETER ResourceGroup
    Where the Azure Bot Service resource is created (usually the Foundry resource's group).
.PARAMETER BotName
    The Azure Bot Service resource name.
.PARAMETER DisplayName
    Shown in Teams and Copilot.
.PARAMETER PublishScope
    Shared (default; "just you", no admin approval, Bot Service RBAC) or Tenant ("people in your
    organization", Microsoft 365 admin approval, Bot Service Tenant). Tenant needs -ConfirmTenantPublish.
.PARAMETER EnablePrivateNetworkRoute
    Default $true: turn on the source-IP-filtered public Activity Protocol route, which a project with
    Pass -EnablePrivateNetworkRoute:$false for a public project (the colon form is needed: a bare
    `-EnablePrivateNetworkRoute $false` is rejected when the script is started with `pwsh -File`).
.PARAMETER ColorIconPath
    The 192x192 PNG colour icon, sent as colorIconBase64. Default: dist/branding/color-192.png when it exists
    (render it with scripts/render-icons.py). An explicit path that is missing, not a PNG, or the wrong size
    is an error; -ColorIconPath '' publishes without a custom colour icon.
.PARAMETER OutlineIconPath
    The 32x32 PNG outline icon (white on transparent, RGBA), sent as outlineIconBase64. Default:
    dist/branding/outline-32.png when it exists. -OutlineIconPath '' publishes without one.
.PARAMETER ConfirmTenantPublish
    Required with -PublishScope Tenant. A tenant-wide publish is submitted for admin approval.
.PARAMETER WhatIf
    Read what is needed (the agent, the tenant), print every request that WOULD change something with
    its body, and change nothing.
#>
#Requires -Version 7.0
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ProjectEndpoint,
    [Parameter(Mandatory)][string]$AgentName,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$BotName,
    [Parameter(Mandatory)][string]$DisplayName,
    [Parameter(Mandatory)][string]$ShortDescription,
    [Parameter(Mandatory)][string]$FullDescription,
    [string]$AppVersion = '1.0.0',
    [ValidateSet('Shared', 'Tenant')][string]$PublishScope = 'Shared',
    [bool]$EnablePrivateNetworkRoute = $true,
    [string]$OutputDir = (Join-Path (Get-Location) 'publish-output'),
    [switch]$ConfirmTenantPublish,
    [string]$SubscriptionId = '',
    [ValidateLength(1, 32)][string]$DeveloperName = 'Tax Credit Copilot (PoC)',
    [string]$ColorIconPath = (Join-Path $PSScriptRoot '..\dist\branding\color-192.png'),
    [string]$OutlineIconPath = (Join-Path $PSScriptRoot '..\dist\branding\outline-32.png'),
    [string]$DeveloperWebsiteUrl = 'https://github.com/jamesiford/tax-credit-copilot-public',
    [string]$PrivacyUrl = 'https://github.com/jamesiford/tax-credit-copilot-public/blob/main/SECURITY.md',
    [string]$TermsOfUseUrl = 'https://github.com/jamesiford/tax-credit-copilot-public/blob/main/DISCLAIMER.md'
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$script:FoundryResource = 'https://ai.azure.com'
$script:BotApi = '2022-09-15'
$script:ChannelApi = '2021-03-01'
$script:MaxVersionAttempts = 50
$script:Temp = New-Object System.Collections.Generic.List[string]
$script:Bound = $PSBoundParameters
$script:Icons = [ordered]@{}
$script:IconFields = @{ Color = 'colorIconBase64'; Outline = 'outlineIconBase64' }

# ------------------------------------------------------------------------------ az

function Invoke-Az {
    <# Runs `az` and returns @{ ExitCode; Out; Err }. Never throws on a non-zero exit. #>
    param([Parameter(Mandatory)][string[]]$Arguments)
    $all = @(& az @Arguments 2>&1)
    $code = $LASTEXITCODE
    $errors = @($all | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { $_.ToString() })
    $lines = @($all | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    return [pscustomobject]@{ ExitCode = $code; Out = ($lines -join "`n").Trim(); Err = ($errors -join "`n").Trim() }
}

function Invoke-AzChecked {
    param([Parameter(Mandatory)][string[]]$Arguments, [Parameter(Mandatory)][string]$What)
    $result = Invoke-Az -Arguments $Arguments
    if ($result.ExitCode -ne 0) { throw "$What failed (az exit code $($result.ExitCode)): $($result.Err)" }
    return $result.Out
}

function Write-JsonTemp([Parameter(Mandatory)]$Object) {
    $path = Join-Path ([IO.Path]::GetTempPath()) ("publish-m365-{0}.json" -f [guid]::NewGuid().ToString('N'))
    $Object | ConvertTo-Json -Depth 20 | Set-Content -Path $path -Encoding utf8 -WhatIf:$false
    $script:Temp.Add($path)
    return $path
}

function Invoke-Rest {
    <# One `az rest` call. -Foundry asks az for a token for the Foundry audience; ARM needs no flag. #>
    param(
        [Parameter(Mandatory)][ValidateSet('get', 'put', 'patch', 'post')][string]$Method,
        [Parameter(Mandatory)][string]$Url,
        $Body = $null,
        [switch]$Foundry,
        [string]$ContentType = '',
        [string]$OutputFile = ''
    )
    $arguments = @('rest', '--method', $Method, '--url', $Url, '--only-show-errors')
    if ($Foundry) { $arguments += @('--resource', $script:FoundryResource) }
    if ($ContentType) { $arguments += @('--headers', "Content-Type=$ContentType") }
    if ($null -ne $Body) { $arguments += @('--body', "@$(Write-JsonTemp $Body)") }
    if ($OutputFile) { $arguments += @('--output-file', $OutputFile) }
    return Invoke-Az -Arguments $arguments
}

function Get-PrintableBody($Body) {
    <# A copy of the body that is safe to print: an icon becomes its length, never its content. #>
    if ($Body -isnot [System.Collections.IDictionary]) { return $Body }
    $copy = [ordered]@{}
    foreach ($key in $Body.Keys) {
        $copy[$key] = if ($key -in $script:IconFields.Values) { "<$($Body[$key].Length) base64 characters>" } else { $Body[$key] }
    }
    return $copy
}

function Write-Request([string]$Method, [string]$Url, $Body) {
    Write-Host "  $($Method.ToUpper()) $Url"
    if ($null -ne $Body) { (Get-PrintableBody $Body | ConvertTo-Json -Depth 20) -split '\r?\n' | ForEach-Object { Write-Host "    $_" } }
}

function Send-Change {
    <# A request that changes something: printed under -WhatIf, sent otherwise. Throws on failure. #>
    param(
        [Parameter(Mandatory)][string]$Description, [Parameter(Mandatory)][string]$Method, [Parameter(Mandatory)][string]$Url,
        $Body = $null, [switch]$Foundry, [string]$ContentType = ''
    )
    Write-Host "-> $Description"
    if (-not $PSCmdlet.ShouldProcess($Url, $Description)) {
        Write-Request $Method $Url $Body
        return $null
    }
    $result = Invoke-Rest -Method $Method -Url $Url -Body $Body -Foundry:$Foundry -ContentType $ContentType
    if ($result.ExitCode -ne 0) { throw "$Description failed: $($result.Err)" }
    return $result
}

# -------------------------------------------------------------------------- checks

function Assert-TenantPublishConfirmed {
    if ($PublishScope -ne 'Tenant') { return }
    if (-not $ConfirmTenantPublish) {
        throw ("-PublishScope Tenant publishes to everyone in the organization and is submitted for Microsoft 365 admin " +
            "approval. Re-run with -ConfirmTenantPublish to proceed, or use the default scope (Shared) to test first.")
    }
    Write-Host 'Tenant scope: this publish is submitted for Microsoft 365 admin approval; it is not visible to the organization until an admin approves it.'
}

function Assert-Parameters {
    if ($ProjectEndpoint -notmatch '^https://[^/]+/api/projects/[^/]+/?$') {
        throw "-ProjectEndpoint must look like https://<resource>.services.ai.azure.com/api/projects/<project>"
    }
    if ($AppVersion -notmatch '^\d+\.\d+\.\d+$') { throw "-AppVersion must be a semantic version such as 1.0.0" }
    foreach ($url in @($DeveloperWebsiteUrl, $PrivacyUrl, $TermsOfUseUrl)) {
        if ($url -notmatch '^https://') { throw "developer, privacy and terms URLs must be https:// ($url)" }
    }
}

function Read-IconPng([string]$Label, [string]$Path, [int]$Size, [bool]$NeedsAlpha) {
    <# Validated before anything is sent: a wrong icon is refused here, not by the service after a version is spent. #>
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "The $Label icon '$Path' does not exist. Render it with: python scripts/render-icons.py" }
    $bytes = [IO.File]::ReadAllBytes($Path)
    $signature = [byte[]](0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    if ($bytes.Length -lt 33 -or (Compare-Object $signature $bytes[0..7] -SyncWindow 0)) { throw "The $Label icon '$Path' is not a PNG file." }
    $width = ([int]$bytes[16] -shl 24) -bor ([int]$bytes[17] -shl 16) -bor ([int]$bytes[18] -shl 8) -bor [int]$bytes[19]
    $height = ([int]$bytes[20] -shl 24) -bor ([int]$bytes[21] -shl 16) -bor ([int]$bytes[22] -shl 8) -bor [int]$bytes[23]
    if ($width -ne $Size -or $height -ne $Size) { throw "The $Label icon must be ${Size}x${Size} pixels; '$Path' is ${width}x${height}." }
    if ($NeedsAlpha -and $bytes[25] -ne 6) { throw "The $Label icon must be an RGBA PNG (a transparent background); '$Path' has colour type $($bytes[25])." }
    return [pscustomobject]@{ Label = $Label; Path = $Path; Bytes = $bytes.Length; Base64 = [Convert]::ToBase64String($bytes) }
}

function Resolve-Icons {
    <# An explicit path must be usable; an unset one is used when the rendered file exists; '' means none. #>
    $wanted = @(
        @{ Key = 'Color'; Param = 'ColorIconPath'; Path = $ColorIconPath; Size = 192; Alpha = $false },
        @{ Key = 'Outline'; Param = 'OutlineIconPath'; Path = $OutlineIconPath; Size = 32; Alpha = $true }
    )
    foreach ($icon in $wanted) {
        $explicit = $script:Bound.ContainsKey($icon.Param)
        if ([string]::IsNullOrWhiteSpace($icon.Path)) { continue }
        if (-not $explicit -and -not (Test-Path -LiteralPath $icon.Path -PathType Leaf)) { continue }
        $script:Icons[$icon.Key] = Read-IconPng -Label $icon.Key.ToLower() -Path $icon.Path -Size $icon.Size -NeedsAlpha $icon.Alpha
    }
    if ($script:Icons.Count -eq 0) { Write-Host 'No custom icons: the listing uses the platform default. Render them with scripts/render-icons.py.' }
    foreach ($key in $script:Icons.Keys) {
        $icon = $script:Icons[$key]
        Write-Host "Icon ($($icon.Label)): $($icon.Path) ($($icon.Bytes) bytes, $($icon.Base64.Length) base64 characters)"
    }
}

function Assert-BotServiceProvider {
    $state = Invoke-Az -Arguments @('provider', 'show', '--namespace', 'Microsoft.BotService', '--query', 'registrationState', '-o', 'tsv')
    if ($state.ExitCode -eq 0 -and $state.Out -eq 'Registered') { return }
    Write-Host 'The Microsoft.BotService resource provider is not registered in this subscription. This script never registers one.'
    Write-Host 'A subscription owner can register it with:'
    Write-Host '    az provider register --namespace Microsoft.BotService'
    exit 1
}

# -------------------------------------------------------------------------- merge

function ConvertTo-Table($Value) {
    if ($null -eq $Value) { return [ordered]@{} }
    $json = $Value | ConvertTo-Json -Depth 20
    return ($json | ConvertFrom-Json -AsHashtable -Depth 20)
}

function Merge-AgentEndpoint {
    <#
    The body of the endpoint PATCH. The service REPLACES protocol_configuration and authorization_schemes,
    so everything the endpoint already has is carried over. Only `activity` (and, when nothing was
    configured at all, `responses`) is added; only the Bot Service scheme is swapped for the scope.
    #>
    param($Current, [string]$Scope, [bool]$PublicRoute)
    $endpoint = ConvertTo-Table $Current
    $protocols = ConvertTo-Table $endpoint['protocol_configuration']
    if ($protocols.Count -eq 0) { $protocols['responses'] = [ordered]@{} }
    $activity = ConvertTo-Table $protocols['activity']
    if ($PublicRoute) { $activity['enable_m365_public_endpoint'] = $true }
    $protocols['activity'] = $activity

    $wanted = if ($Scope -eq 'Tenant') { 'BotServiceTenant' } else { 'BotServiceRbac' }
    $other = if ($Scope -eq 'Tenant') { 'BotServiceRbac' } else { 'BotServiceTenant' }
    $schemes = @()
    foreach ($scheme in @($endpoint['authorization_schemes'])) {
        if ($null -ne $scheme -and $scheme['type'] -ne $other) { $schemes += , $scheme }
    }
    if (-not ($schemes | Where-Object { $_['type'] -eq $wanted })) { $schemes += , ([ordered]@{ type = $wanted }) }
    return [ordered]@{ agent_endpoint = [ordered]@{ protocol_configuration = $protocols; authorization_schemes = $schemes } }
}

function Get-NextPatchVersion([string]$Version) {
    $parts = $Version.Split('.')
    return '{0}.{1}.{2}' -f $parts[0], $parts[1], ([int]$parts[2] + 1)
}

# -------------------------------------------------------------------------- steps

function Get-AgentDefinition {
    $url = "$($ProjectEndpoint.TrimEnd('/'))/agents/${AgentName}?api-version=v1"
    $result = Invoke-Rest -Method get -Url $url -Foundry
    if ($result.ExitCode -ne 0) { throw "Could not read agent '$AgentName' ($url): $($result.Err)" }
    $agent = $result.Out | ConvertFrom-Json -AsHashtable -Depth 20
    $identity = $agent['instance_identity']
    $clientId = if ($identity) { $identity['client_id'] } else { $null }
    if ([string]::IsNullOrWhiteSpace($clientId)) { throw "Agent '$AgentName' has no instance_identity.client_id; is it deployed and active?" }
    return @{ Agent = $agent; ClientId = $clientId }
}

function Set-BotService([string]$Subscription, [string]$ClientId, [string]$TenantId) {
    $base = "https://management.azure.com/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.BotService/botServices/$BotName"
    $bot = [ordered]@{
        location = 'global'; kind = 'azurebot'; sku = [ordered]@{ name = 'F0' }
        properties = [ordered]@{
            displayName = $DisplayName
            endpoint = "$($ProjectEndpoint.TrimEnd('/'))/agents/$AgentName/endpoint/protocols/activityProtocol?api-version=v1"
            msaAppId = $ClientId; msaAppTenantId = $TenantId; msaAppType = 'SingleTenant'; publicNetworkAccess = 'Disabled'
        }
    }
    $channel = [ordered]@{ location = 'global'; properties = [ordered]@{ channelName = 'MsTeamsChannel' } }
    Send-Change -Description "Create or update the Azure Bot Service resource '$BotName'" -Method put -Url "${base}?api-version=$($script:BotApi)" -Body $bot | Out-Null
    Send-Change -Description "Enable the Microsoft Teams channel on '$BotName'" -Method put -Url "$base/channels/MsTeamsChannel?api-version=$($script:ChannelApi)" -Body $channel | Out-Null
    return "/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.BotService/botServices/$BotName"
}

function New-PublishBody([string]$BotArmId, [string]$Version) {
    $body = [ordered]@{
        agentDisplayName = $DisplayName; botServiceArmId = $BotArmId; publishScope = $PublishScope; publishAsAutopilot = $false
        appVersion = $Version; shortDescription = $ShortDescription; fullDescription = $FullDescription
        developerName = $DeveloperName; developerWebsiteUrl = $DeveloperWebsiteUrl; privacyUrl = $PrivacyUrl; termsOfUseUrl = $TermsOfUseUrl
    }
    foreach ($key in $script:Icons.Keys) { $body[$script:IconFields[$key]] = $script:Icons[$key].Base64 }
    return $body
}

function Publish-Agent([string]$BotArmId) {
    $url = "$($ProjectEndpoint.TrimEnd('/'))/agents/$AgentName/microsoft365/publish?api-version=v1"
    $version = $AppVersion
    for ($attempt = 1; $attempt -le $script:MaxVersionAttempts; $attempt++) {
        $body = New-PublishBody $BotArmId $version
        Write-Host "-> Publish version $version to Microsoft 365 ($PublishScope)"
        if (-not $PSCmdlet.ShouldProcess($url, "Publish version $version ($PublishScope)")) {
            Write-Request 'post' $url $body
            return @{ Version = $version; TitleId = $null; Body = $body }
        }
        $result = Invoke-Rest -Method post -Url $url -Body $body -Foundry
        if ($result.ExitCode -eq 0) {
            $title = ($result.Out | ConvertFrom-Json -AsHashtable -Depth 20)['titleId']
            if ([string]::IsNullOrWhiteSpace($title)) { throw "The publish call did not return a titleId, so it is NOT reported as published. Response: $($result.Out)" }
            return @{ Version = $version; TitleId = $title; Body = $body }
        }
        if (($result.Err + $result.Out) -notmatch 'already exists') { throw "Publish failed: $($result.Err) $($result.Out)" }
        $next = Get-NextPatchVersion $version
        Write-Host "   version $version is already published; trying $next"
        $version = $next
    }
    throw "No unused version found after $($script:MaxVersionAttempts) attempts starting at $AppVersion."
}

function Save-AppPackage($Body) {
    $url = "$($ProjectEndpoint.TrimEnd('/'))/agents/$AgentName/microsoft365/zip?api-version=v1"
    $zip = Join-Path $OutputDir 'appPackage.zip'
    Write-Host '-> Download the validated app package'
    if (-not $PSCmdlet.ShouldProcess($url, "Download the app package to $zip")) {
        Write-Request 'post' $url $Body
        return
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $result = Invoke-Rest -Method post -Url $url -Body $Body -Foundry -OutputFile $zip
    if ($result.ExitCode -ne 0 -or -not (Test-Path $zip)) { throw "Could not download the app package: $($result.Err)" }
    Write-ManifestSummary $zip
}

function Write-ManifestSummary([string]$Zip) {
    $folder = Join-Path $OutputDir 'appPackage'
    if (Test-Path $folder) { Remove-Item $folder -Recurse -Force }
    Expand-Archive -Path $Zip -DestinationPath $folder -Force
    $manifest = Get-Content (Join-Path $folder 'manifest.json') -Raw | ConvertFrom-Json
    Write-Host "   package: $Zip"
    Write-Host "   manifest: name=$($manifest.name.short) version=$($manifest.version) id=$($manifest.id) developer=$($manifest.developer.name)"
    Write-Host "   bots: $(@($manifest.bots).Count); files: $((Get-ChildItem $folder -Recurse -File | Measure-Object).Count)"
}

function Write-NextSteps($Published) {
    if ($Published.TitleId) {
        Write-Host "Published version $($Published.Version) (titleId $($Published.TitleId))."
        if ($PublishScope -eq 'Tenant') {
            Write-Host 'Next: a Microsoft 365 admin approves the agent at https://admin.cloud.microsoft/?#/agents/all/requested. It then appears under "Built by your org".'
        }
        else {
            Write-Host 'Next: open Microsoft Teams or Microsoft 365 Copilot, find the agent under "Your agents", and share its link to add it to a chat.'
        }
        Write-Host 'Test it by sending "/whoami" if CHANNEL_DEBUG_WHOAMI is on for the agent; see docs/m365-channel/PUBLISHING.md.'
    }
    else {
        Write-Host 'WhatIf: nothing was published.'
    }
}

# ---------------------------------------------------------------------------- main

try {
    Assert-TenantPublishConfirmed
    Assert-Parameters
    Resolve-Icons
    Assert-BotServiceProvider
    $tenant = Invoke-AzChecked -Arguments @('account', 'show', '--query', 'tenantId', '-o', 'tsv') -What 'Reading the tenant id'
    $subscription = if ($SubscriptionId) { $SubscriptionId } else { Invoke-AzChecked -Arguments @('account', 'show', '--query', 'id', '-o', 'tsv') -What 'Reading the subscription id' }
    Write-Host "Publishing agent '$AgentName' (scope $PublishScope); bot '$BotName' in resource group '$ResourceGroup'."

    $definition = Get-AgentDefinition
    $botArmId = Set-BotService -Subscription $subscription -ClientId $definition.ClientId -TenantId $tenant
    if ($EnablePrivateNetworkRoute) {
        $patch = Merge-AgentEndpoint -Current $definition.Agent['agent_endpoint'] -Scope $PublishScope -PublicRoute $true
        Send-Change -Description 'Enable the Activity Protocol route and the Bot Service authorization scheme (merged with the existing settings)' `
            -Method patch -Url "$($ProjectEndpoint.TrimEnd('/'))/agents/${AgentName}?api-version=v1" -Body $patch -Foundry -ContentType 'application/merge-patch+json' | Out-Null
    }
    else {
        Write-Host 'Skipping the endpoint PATCH (-EnablePrivateNetworkRoute is off): publishing adds the activity protocol and the authorization scheme itself on a project with public network access.'
    }
    $published = Publish-Agent -BotArmId $botArmId
    Save-AppPackage -Body $published.Body
    Write-NextSteps $published
}
finally {
    foreach ($path in $script:Temp) { Remove-Item $path -Force -ErrorAction SilentlyContinue -WhatIf:$false }
}
