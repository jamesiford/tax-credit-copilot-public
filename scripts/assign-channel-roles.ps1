<#
.SYNOPSIS
    Assign the Entra app roles the Microsoft 365 channel needs. [CH-13]

.DESCRIPTION
    Terraform cannot make directory role assignments, so this is the operator's step.
    Every identifier is a parameter; none is written into this file. Each assignment is
    idempotent (an existing one is reported and left alone), supports -WhatIf, and goes
    through `az rest` against Microsoft Graph with the caller's own sign-in.

      -GatewayIdentityPrincipalId   gets  TCC.Agent  on the API registration
                                    (the gateway calls the API as an agent)
      -AgentIdentityPrincipalId     gets  Channel.Invoke  on the gateway registration
                                    (the hosted orchestrator calls the gateway)
      -GrantGraphGroupMemberRead    also gives the gateway identity (and, with -ApiIdentityPrincipalId,
                                    the API identity: it enforces the writer entitlement itself) the
                                    Microsoft Graph application role GroupMember.Read.All (nothing
                                    else), which the Entra-group writer check needs
      -GrantUserReadBasic           gives the gateway identity the Microsoft Graph application role
                                    User.ReadBasic.All (display name and UPN of a user, nothing
                                    else), which CHANNEL_RESOLVE_DISPLAY_NAMES needs. Needs
                                    -GatewayIdentityPrincipalId. ADMIN ACTION: the signed-in
                                    account must be able to grant application permissions
                                    (Privileged Role Administrator or Global Administrator);
                                    otherwise the script prints the exact command for one,
                                    exactly as it does for the other roles. Idempotent: an
                                    existing assignment is reported and left alone

    When Graph answers Forbidden the script does not try anything else: it prints the exact
    commands for someone who can assign app roles, and exits 2 so a caller can tell
    "denied, here is the hand-off" from a failure.

.EXAMPLE
    pwsh scripts/assign-channel-roles.ps1 -ApiApplicationId <id> -GatewayApplicationId <id> `
        -GatewayIdentityPrincipalId <oid> -AgentIdentityPrincipalId <oid> -GrantGraphGroupMemberRead
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ApiApplicationId,
    [Parameter(Mandatory)][string]$GatewayApplicationId,
    [string]$GatewayIdentityPrincipalId,
    [string]$AgentIdentityPrincipalId,
    [string]$ApiIdentityPrincipalId,
    [switch]$GrantGraphGroupMemberRead,
    [switch]$GrantUserReadBasic
)

$ErrorActionPreference = 'Stop'
$graph = 'https://graph.microsoft.com/v1.0'
$graphApplicationId = '00000003-0000-0000-c000-000000000000'
$script:handoff = [System.Collections.Generic.List[string]]::new()

function Invoke-Graph([string]$Method, [string]$Path, $Body) {
    $arguments = @('rest', '--method', $Method, '--url', "$graph$Path", '--only-show-errors', '-o', 'json')
    $bodyFile = $null
    if ($null -ne $Body) {
        $bodyFile = New-TemporaryFile
        [IO.File]::WriteAllText($bodyFile.FullName, ($Body | ConvertTo-Json -Compress))
        $arguments += @('--headers', 'Content-Type=application/json', '--body', "@$($bodyFile.FullName)")
    }
    try {
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            $text = & az @arguments 2>&1
            if ($LASTEXITCODE -eq 0 -or ($text | Out-String) -notmatch 'RemoteDisconnected|Connection aborted|timed out') { break }
            Start-Sleep -Seconds (2 * $attempt)
        }
    } finally { if ($bodyFile) { Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue } }
    if ($LASTEXITCODE -ne 0) {
        $message = ($text | Out-String).Trim()
        $denied = $message -match 'Authorization_RequestDenied|Forbidden|Insufficient privileges|403'
        throw [pscustomobject]@{ Denied = $denied; Message = $message }
    }
    if ($text) { return ($text | Out-String | ConvertFrom-Json) }
}

function Get-ServicePrincipal([string]$ApplicationId) {
    $found = Invoke-Graph GET "/servicePrincipals?`$filter=appId eq '$ApplicationId'&`$select=id,displayName,appRoles"
    if (-not $found.value -or $found.value.Count -ne 1) { throw "No single service principal for application $ApplicationId." }
    return $found.value[0]
}

function Add-Handoff([string]$ResourceId, [string]$PrincipalId, [string]$RoleId) {
    $body = (@{ principalId = $PrincipalId; resourceId = $ResourceId; appRoleId = $RoleId } | ConvertTo-Json -Compress).Replace('"', '\"')
    $script:handoff.Add("az rest --method POST --url $graph/servicePrincipals/$ResourceId/appRoleAssignedTo --headers Content-Type=application/json --body `"$body`"")
}

function Grant-AppRole($Resource, [string]$RoleValue, [string]$PrincipalId, [string]$Label) {
    $role = $Resource.appRoles | Where-Object { $_.value -eq $RoleValue -and $_.allowedMemberTypes -contains 'Application' } | Select-Object -First 1
    if (-not $role) { throw "$($Resource.displayName) has no application role $RoleValue." }
    $existing = Invoke-Graph GET "/servicePrincipals/$($Resource.id)/appRoleAssignedTo?`$top=999"
    if ($existing.value | Where-Object { $_.principalId -eq $PrincipalId -and $_.appRoleId -eq $role.id }) {
        Write-Host "  already assigned: $RoleValue -> $Label"
        return
    }
    if (-not $PSCmdlet.ShouldProcess("$Label", "assign $RoleValue on $($Resource.displayName)")) { return }
    try {
        Invoke-Graph POST "/servicePrincipals/$($Resource.id)/appRoleAssignedTo" @{ principalId = $PrincipalId; resourceId = $Resource.id; appRoleId = $role.id } | Out-Null
        Write-Host "  assigned: $RoleValue -> $Label" -ForegroundColor Green
    } catch {
        if (-not $_.TargetObject.Denied) { throw $_.TargetObject.Message }
        Write-Host "  DENIED: $RoleValue -> $Label (an administrator must make this assignment)" -ForegroundColor Yellow
        Add-Handoff $Resource.id $PrincipalId $role.id
    }
}

try {
    $api = Get-ServicePrincipal $ApiApplicationId
    $gateway = Get-ServicePrincipal $GatewayApplicationId
    if ($GatewayIdentityPrincipalId) {
        Write-Host "Gateway identity" -ForegroundColor Cyan
        Grant-AppRole $api 'TCC.Agent' $GatewayIdentityPrincipalId 'the gateway identity'
        if ($GrantGraphGroupMemberRead) {
            Grant-AppRole (Get-ServicePrincipal $graphApplicationId) 'GroupMember.Read.All' $GatewayIdentityPrincipalId 'the gateway identity'
        }
        if ($GrantUserReadBasic) {
            Grant-AppRole (Get-ServicePrincipal $graphApplicationId) 'User.ReadBasic.All' $GatewayIdentityPrincipalId 'the gateway identity'
        }
    } elseif ($GrantUserReadBasic) {
        throw '-GrantUserReadBasic needs -GatewayIdentityPrincipalId: the role goes to the gateway identity.'
    }
    if ($AgentIdentityPrincipalId) {
        Write-Host "Agent identity" -ForegroundColor Cyan
        Grant-AppRole $gateway 'Channel.Invoke' $AgentIdentityPrincipalId 'the agent identity'
    }
    if ($ApiIdentityPrincipalId -and $GrantGraphGroupMemberRead) {
        Write-Host "API identity (it enforces the writer entitlement itself)" -ForegroundColor Cyan
        Grant-AppRole (Get-ServicePrincipal $graphApplicationId) 'GroupMember.Read.All' $ApiIdentityPrincipalId 'the API identity'
    }
} catch {
    $detail = if ($_.TargetObject -and $_.TargetObject.Message) { $_.TargetObject.Message } else { $_.Exception.Message }
    Write-Error $detail
    exit 1
}

if ($script:handoff.Count -gt 0) {
    Write-Host "`nADMIN ACTIONS: run these as someone who can assign app roles:" -ForegroundColor Yellow
    $script:handoff | ForEach-Object { Write-Host $_ }
    exit 2
}
