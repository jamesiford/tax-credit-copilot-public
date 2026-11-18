<#
.SYNOPSIS
  Prints a per-stage timing table for one queued client calculation at 100k, 400k and 1M payroll rows, with no live lakehouse.

.DESCRIPTION
  Runs the opt-in benchmark in TaxCredit.Api.Tests (TCC_RUN_BENCH=1): a synthetic client in the real source shape behind a fake analytics
  transport, the real worker executor, SQLite operational store. Spans come from TaxCredit.Run (RunSpans); times are exclusive, so the rows add up.
  Also writes dotnet\artifacts\bench\bench-<label>.txt and, with -DumpGold, a dump of every stored Gold row per size.

.EXAMPLE
  .\dotnet\bench-run.ps1                      # three sizes
  .\dotnet\bench-run.ps1 -Sizes 100000 -Label before
#>
param(
    [long[]]$Sizes = @(100000, 400000, 1000000),
    [string]$Label = 'run',
    [string]$DumpGold,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:TCC_RUN_BENCH = '1'
$env:TCC_BENCH_SIZES = ($Sizes -join ',')
$env:TCC_BENCH_LABEL = $Label
if ($DumpGold) { New-Item -ItemType Directory -Force $DumpGold | Out-Null; $env:TCC_BENCH_DUMP = (Resolve-Path $DumpGold).Path }
$testArgs = @('test', 'tests\TaxCredit.Api.Tests', '--filter', 'Category=bench', '--nologo')
if ($NoBuild) { $testArgs += '--no-build' }
& dotnet @testArgs | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The benchmark failed; rerun with: dotnet test tests\TaxCredit.Api.Tests --filter Category=bench' }
Get-Content (Join-Path $PSScriptRoot "artifacts\bench\bench-$Label.txt")
