<#
.SYNOPSIS
    Pause (or resume) the PoC's compute. [CH-13]

.DESCRIPTION
    Stops the apps in the PoC resource group and scales the shared App Service plan down to
    a cheap tier; -Resume reverses it. The plan's original SKU is kept in a tag on the plan
    (`pause-sku`), so resume needs no arguments. Nothing is deleted and no data moves.

    It deliberately does NOT touch the Fabric capacity: other workspaces share it. The
    command to pause it is printed for the owner to run if and when that is right.

    Foundry (pay per token) and Bot Service (free tier) have no idle compute to pause.

.EXAMPLE
    pwsh scripts/poc-pause.ps1 -ResourceGroup <rg>            # pause
    pwsh scripts/poc-pause.ps1 -ResourceGroup <rg> -Resume    # resume
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ResourceGroup,
    [switch]$Resume,
    [string]$PausedSku = 'B1'
)

$ErrorActionPreference = 'Stop'

function Invoke-Az {
    $out = & az @args --only-show-errors -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed: $out" }
    if ($out) { return ($out | Out-String | ConvertFrom-Json) }
}

$plans = @(Invoke-Az appservice plan list -g $ResourceGroup)
if ($plans.Count -ne 1) { throw "Expected exactly one App Service plan in $ResourceGroup, found $($plans.Count)." }
$plan = $plans[0]
$apps = @(Invoke-Az webapp list -g $ResourceGroup)

if ($Resume) {
    $original = $plan.tags.'pause-sku'
    if (-not $original) { throw 'The plan carries no pause-sku tag; nothing was paused by this script.' }
    if ($PSCmdlet.ShouldProcess($plan.name, "scale back to $original")) {
        Invoke-Az appservice plan update -g $ResourceGroup -n $plan.name --sku $original | Out-Null
        Invoke-Az tag update --resource-id $plan.id --operation Delete --tags pause-sku | Out-Null
    }
    foreach ($app in $apps) {
        if ($PSCmdlet.ShouldProcess($app.name, 'start')) { Invoke-Az webapp start -g $ResourceGroup -n $app.name | Out-Null }
    }
    Write-Host "Resumed: plan back on $original, $($apps.Count) apps started. Allow a few minutes for health checks."
    return
}

foreach ($app in $apps) {
    if ($PSCmdlet.ShouldProcess($app.name, 'stop')) { Invoke-Az webapp stop -g $ResourceGroup -n $app.name | Out-Null }
}
if ($plan.sku.name -ne $PausedSku -and $PSCmdlet.ShouldProcess($plan.name, "scale from $($plan.sku.name) to $PausedSku")) {
    Invoke-Az tag update --resource-id $plan.id --operation Merge --tags "pause-sku=$($plan.sku.name)" | Out-Null
    Invoke-Az appservice plan update -g $ResourceGroup -n $plan.name --sku $PausedSku | Out-Null
}
Write-Host "Paused: $($apps.Count) apps stopped, plan on $PausedSku. Resume with: pwsh scripts/poc-pause.ps1 -ResourceGroup $ResourceGroup -Resume"
Write-Host 'The Fabric capacity is shared with other workspaces and was NOT touched. To pause it (owner decision):'
Write-Host '  az fabric capacity suspend --capacity-name <capacity> --resource-group <its resource group>'
