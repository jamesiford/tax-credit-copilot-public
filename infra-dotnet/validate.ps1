[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Check {
    param([string]$Tool, [string[]]$Arguments)
    & $Tool @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Tool validation failed with exit code $LASTEXITCODE." }
}

$source = $PSScriptRoot
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$destination = Join-Path $source ".validation\clean-$stamp"
if (Test-Path $destination) { throw 'Clean validation destination already exists.' }
New-Item -ItemType Directory -Path $destination | Out-Null

# Copy an allowlist, not the worktree: local backend/variable files never enter validation.
Get-ChildItem -LiteralPath $source -File -Force |
    Where-Object { $_.Extension -eq '.tf' -or $_.Name -in @('.terraform.lock.hcl', '.tflint.hcl', 'guard_offline.py') } |
    Copy-Item -Destination $destination
foreach ($directory in @('modules', 'tests')) {
    Copy-Item -LiteralPath (Join-Path $source $directory) -Destination $destination -Recurse
}

Write-Output "Clean copy: $destination"
$env:CHECKPOINT_DISABLE = '1'
$env:TF_IN_AUTOMATION = 'true'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location $destination
try {
    Invoke-Check 'python' @('guard_offline.py')
    Invoke-Check 'python' @('-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-q')
    Invoke-Check 'terraform' @('init', '-backend=false', '-input=false', '-no-color')
    Invoke-Check 'terraform' @('fmt', '-check', '-recursive')
    Invoke-Check 'terraform' @('validate', '-no-color')
    Invoke-Check 'terraform' @('test', '-no-color')
    Invoke-Check 'tflint' @('--recursive', '--no-color')
}
finally {
    Pop-Location
}
