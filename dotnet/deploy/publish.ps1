param(
    [ValidateSet('api', 'worker', 'gateway', 'orchestrator', 'all')]
    [string] $Service = 'all',
    [string] $Output,
    [string] $Runtime,
    [string] $Python = $(if ($env:DEPLOY_PYTHON) { $env:DEPLOY_PYTHON } else { 'python' })
)
$ErrorActionPreference = 'Stop'
$arguments = @((Join-Path $PSScriptRoot 'publish.py'), '--service', $Service)
if ($Output) { $arguments += @('--output', $Output) }
if ($Runtime) { $arguments += @('--runtime', $Runtime) }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Pinned publication failed.' }
