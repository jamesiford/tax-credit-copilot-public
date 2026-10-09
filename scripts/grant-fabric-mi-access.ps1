<#
.SYNOPSIS
    Grant the API's managed identity a role on an EXISTING Fabric workspace,
    for deployments where Terraform does not manage Fabric access.

.DESCRIPTION
    Terraform grants the workspace role itself when `manage_fabric_access` is
    on (infra/modules/fabric). Use this script when it is off, typically an
    enterprise deployment against a customer-owned workspace. Two things are
    needed before the API can read OneLake and connect to the Warehouse:

      1. A Fabric WORKSPACE ROLE for the API identity. Fabric has its own
         permission model; an Azure role assignment on the capacity does not
         grant it. The default matches Terraform's `fabric_workspace_role`
         (Contributor): Viewer alone cannot read OneLake files. Schema-level
         Warehouse grants are separate: scripts/grant-warehouse-sql.py.

      2. The tenant setting "Service principals can use Fabric APIs". Without
         it the role above exists and OneLake still returns 401. It is a Fabric
         admin-portal toggle with no API, so this script checks and reports it
         rather than setting it.

    Until both are in place the deployed API fails on every data path while
    `/api/health` keeps returning 200, the same signature a paused capacity
    produces (see docs/architecture/RUNBOOK.md).

.NOTES
    Requires the signed-in user to be a Fabric workspace Admin.
    Idempotent: re-running an existing assignment updates it in place.

    Run:  az login --tenant <fabric-tenant>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$WorkspaceId,
    [ValidateSet('Admin', 'Member', 'Contributor', 'Viewer')]
    [string]$WorkspaceRole = 'Contributor',
    # Defaults to the API identity Terraform creates (id-tcc-api-<suffix>);
    # the web identity carries telemetry only and must not be granted.
    [string]$IdentityName,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

if (-not $IdentityName) {
    $IdentityName = (az identity list -g $ResourceGroup --query "[?starts_with(name, 'id-tcc-api-')].name | [0]" -o tsv)
    if (-not $IdentityName) { throw "No API managed identity (id-tcc-api-*) found in $ResourceGroup." }
}
$principalId = az identity show -n $IdentityName -g $ResourceGroup --query principalId -o tsv
$clientId    = az identity show -n $IdentityName -g $ResourceGroup --query clientId -o tsv
if (-not $principalId) { throw "Could not resolve principalId for $IdentityName." }

Write-Host "Managed identity : $IdentityName" -ForegroundColor Cyan
Write-Host "  principalId    : $principalId"
Write-Host "  clientId       : $clientId"
Write-Host "Fabric workspace : $WorkspaceId  (role: $WorkspaceRole)" -ForegroundColor Cyan

if ($WhatIf) {
    Write-Host 'WhatIf: no changes made.' -ForegroundColor Yellow
    exit 0
}

$token = az account get-access-token --resource 'https://api.fabric.microsoft.com' --query accessToken -o tsv
if (-not $token) { throw 'Could not acquire a Fabric API token.' }

$headers = @{ Authorization = "Bearer $token"; 'Content-Type' = 'application/json' }
$uri     = "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/roleAssignments"
$body    = @{
    principal = @{ id = $principalId; type = 'ServicePrincipal' }
    role      = $WorkspaceRole
} | ConvertTo-Json -Depth 5

try {
    Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $body | Out-Null
    Write-Host "Granted $WorkspaceRole to $IdentityName." -ForegroundColor Green
}
catch {
    # An existing assignment is success, not failure — this script is meant to
    # be safe to re-run.
    if ($_.Exception.Response.StatusCode.value__ -eq 409) {
        Write-Host "Already assigned; nothing to change." -ForegroundColor Green
    }
    else {
        throw
    }
}

Write-Host ''
Write-Host 'Still to confirm by hand, in the Fabric admin portal:' -ForegroundColor Yellow
Write-Host '  Tenant settings -> Developer settings ->'
Write-Host '    "Service principals can use Fabric APIs"  = Enabled'
Write-Host '  It has no API. Without it the role above exists and OneLake still 401s.'
