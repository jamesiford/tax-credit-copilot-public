<#
.SYNOPSIS
    What did the platform actually receive for my last Teams / Copilot message? [CH-13]

.DESCRIPTION
    Run it after typing in Teams or Copilot Chat. It prints, from the per-user audit
    (scripts/channel-audit.py --detail), every channel request since -Since for one person:
    the acting object id, the display name (or "(name not provided)"), the channel, the
    identity assurance, the numeric-guard status and the correlation id. Then it calls the
    gateway's channel_ping with YOUR own sign-in, so you can compare what a delegated caller
    looks like with what the agent path recorded for the same person (spikes S1 and S2).

    Nothing is changed. No token is printed. Needs `az login`, the azd environment of the
    deployment (for the warehouse and gateway addresses) and the repo's .venv.

.EXAMPLE
    pwsh scripts/channel-smoke.ps1 -Since '2026-11-03T16:00:00Z'
    pwsh scripts/channel-smoke.ps1 -Since (Get-Date).AddMinutes(-10) -UserOid <oid-from-/whoami>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][datetime]$Since,
    [string]$UserOid,
    [string]$GatewayBaseUrl,
    [string]$GatewayAudience
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

function Import-AzdEnvironment {
    foreach ($line in (azd env get-values 2>$null)) {
        if ($line -match '^([^=]+)="?(.*?)"?$' -and -not [Environment]::GetEnvironmentVariable($Matches[1])) {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
        }
    }
}

function Get-DelegatedToken([string]$Audience) {
    $token = az account get-access-token --scope "$Audience/Channel.Access" --query accessToken -o tsv 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $token) { throw "Could not get a delegated token for $Audience (az login as a user the gateway registration allows)." }
    return $token
}

Import-AzdEnvironment
if (-not $UserOid) { $UserOid = az ad signed-in-user show --query id -o tsv }
if (-not $GatewayBaseUrl) { $GatewayBaseUrl = $env:CHANNEL_BASE_URL }
if (-not $GatewayAudience) { $GatewayAudience = $env:TCC_CHANNEL_GATEWAY_AUDIENCE }
foreach ($required in 'WAREHOUSE_SERVER', 'WAREHOUSE_DATABASE') {
    if (-not [Environment]::GetEnvironmentVariable($required)) { throw "$required is not set; run from the repo with the azd environment selected." }
}

$env:CHANNEL_STORE = 'warehouse'
# Not `$since`: PowerShell variable names are case-insensitive, so that would assign to the [datetime]
# parameter $Since above and turn the ISO text back into a culture-formatted date channel-audit.py rejects. [CH-14]
$sinceIso = $Since.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Write-Host "== Audit rows for $UserOid since $sinceIso" -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot 'channel-audit.py') --user $UserOid --since $sinceIso --detail
if ($LASTEXITCODE -ne 0) { throw "channel-audit.py exited $LASTEXITCODE" }

if ($GatewayBaseUrl -and $GatewayAudience) {
    Write-Host "`n== channel_ping with your own delegated token (what the gateway sees of you directly)" -ForegroundColor Cyan
    $headers = @{ Authorization = "Bearer $(Get-DelegatedToken $GatewayAudience)"; 'Content-Type' = 'application/json' }
    try {
        $ping = Invoke-RestMethod -Method Post -Uri "$($GatewayBaseUrl.TrimEnd('/'))/channel/v1/tools/channel_ping" -Headers $headers -Body '{}'
        $ping.facts | ConvertTo-Json -Depth 6
    } catch {
        Write-Host "channel_ping unavailable: $($_.Exception.Message) (the gateway offers it only with CHANNEL_DEBUG_WHOAMI=true)" -ForegroundColor Yellow
    }
}
