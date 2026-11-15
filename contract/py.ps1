# Runs a contract tool with the oracle interpreter (Python 3.12, the version the product runs on) from <worktree>\backend.
#   .\contract\py.ps1 -m contract.inventory.generate --check
#   $env:CONTRACT_PYTHON = '<other python>'; .\contract\py.ps1 -m contract.capture --check --allow-other-python   # cross-check only
# CONTRACT_PYTHON overrides the default, which is the 3.12 oracle environment (see contract/README.md to create it). The capture,
# replay and harness modules refuse to run on anything but 3.12 unless --allow-other-python is passed. The code imported is this
# worktree's (verified by contract.harness.hermetic.assert_checkout).
param([Parameter(ValueFromRemainingArguments = $true)] $Args)
$root = Split-Path -Parent $PSScriptRoot
$python = if ($env:CONTRACT_PYTHON) { $env:CONTRACT_PYTHON } else { 'C:\Projects\py312-oracle\.venv\Scripts\python.exe' }
if (-not (Test-Path $python)) {
    Write-Error "contract: interpreter not found: $python. Create the 3.12 oracle environment (contract/README.md) or set CONTRACT_PYTHON."
    exit 2
}
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $root
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location (Join-Path $root 'backend')
try { & $python @Args; exit $LASTEXITCODE } finally { Pop-Location }
