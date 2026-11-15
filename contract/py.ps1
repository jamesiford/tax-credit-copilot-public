# Runs a contract tool with the product's interpreter from <worktree>\backend.
#   .\contract\py.ps1 -m contract.inventory.generate --check
# The interpreter is the main checkout's venv; the code imported is this worktree's (verified by contract.harness.hermetic.assert_checkout).
param([Parameter(ValueFromRemainingArguments = $true)] $Args)
$root = Split-Path -Parent $PSScriptRoot
$python = if ($env:CONTRACT_PYTHON) { $env:CONTRACT_PYTHON } else { 'C:\Projects\GitHub\tax-credit-copilot-public\.venv\Scripts\python.exe' }
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $root
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location (Join-Path $root 'backend')
try { & $python @Args; exit $LASTEXITCODE } finally { Pop-Location }
