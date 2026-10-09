<#
.SYNOPSIS
    White-label deny-list check over every git-tracked file. [WL-12]

.DESCRIPTION
    Case-insensitive, over tracked text files, excluding docs/platform-v2/**
    (internal planning, removed before export) and the root AGENTS.md (same
    reason). Binary files (images, PDFs, Office documents) are skipped here —
    scripts/audit-export.py scans those, including the XML inside Office zips
    and extracted PDF text.

    The deny-list is WL-12's exact list. `john` is deliberately NOT included:
    it is reviewed by hand, case-sensitive, in comments and docs only, because
    it is a common word as well as a name.

    This script's own source, scripts/audit-export.py (which also spells out
    the deny-list) and the allow-list file itself are excluded from the scan:
    they necessarily contain the deny-list as data, not as prose about a real
    customer or person.

.PARAMETER Enforce
    Exit 1 if any non-allow-listed hit is found. Without it, this prints the
    report and exits 0 — the mode CI runs in Phase B until B07 flips it on.

.PARAMETER AllowListPath
    Defaults to scripts/whitelabel-allowlist.txt, next to this script.

.EXAMPLE
    pwsh scripts/check-whitelabel.ps1
    pwsh scripts/check-whitelabel.ps1 -Enforce
#>
[CmdletBinding()]
param(
    [switch]$Enforce,
    [string]$AllowListPath
)

$ErrorActionPreference = 'Stop'

if (-not $AllowListPath) {
    $AllowListPath = Join-Path $PSScriptRoot 'whitelabel-allowlist.txt'
}

$repoRoot = (git rev-parse --show-toplevel).Trim()
Push-Location $repoRoot
try {
    $denyTerms = @(
        [pscustomobject]@{ Term = 'experian';                Pattern = [regex]::Escape('experian') }
        [pscustomobject]@{ Term = 'skowronski';               Pattern = [regex]::Escape('skowronski') }
        [pscustomobject]@{ Term = 'wiseman';                  Pattern = [regex]::Escape('wiseman') }
        [pscustomobject]@{ Term = 'tichina';                  Pattern = [regex]::Escape('tichina') }
        [pscustomobject]@{ Term = 'anusha';                   Pattern = [regex]::Escape('anusha') }
        [pscustomobject]@{ Term = 'mohsin';                   Pattern = [regex]::Escape('mohsin') }
        [pscustomobject]@{ Term = 'incentiveworks';           Pattern = [regex]::Escape('incentiveworks') }
        [pscustomobject]@{ Term = 'ehc';                      Pattern = [regex]::Escape('ehc') }
        [pscustomobject]@{ Term = 'bcs record';               Pattern = [regex]::Escape('bcs record') }
        [pscustomobject]@{ Term = 'flex_gold';                Pattern = [regex]::Escape('flex_gold') }
        [pscustomobject]@{ Term = 'flex_ops';                 Pattern = [regex]::Escape('flex_ops') }
        [pscustomobject]@{ Term = 'force ?flex';              Pattern = 'force ?flex' }
        [pscustomobject]@{ Term = 'fordjames';                Pattern = [regex]::Escape('fordjames') }
        [pscustomobject]@{ Term = 'MngEnvMCAP';               Pattern = [regex]::Escape('MngEnvMCAP') }
        [pscustomobject]@{ Term = 'experian-tax-credit-demo'; Pattern = [regex]::Escape('experian-tax-credit-demo') }
    )

    $selfExcluded = @(
        'scripts/check-whitelabel.ps1'
        'scripts/audit-export.py'
        'scripts/whitelabel-allowlist.txt'
    )

    $binaryExts = @(
        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.pdf',
        '.docx', '.xlsx', '.pptx', '.doc', '.ppt', '.xls', '.zip', '.whl'
    )

    $files = (git ls-files -z) -split "`0" | Where-Object { $_ }
    $files = $files | Where-Object {
        $_ -notmatch '^docs/platform-v2/' -and
        $_ -ne 'AGENTS.md' -and
        ($selfExcluded -notcontains $_) -and
        ($binaryExts -notcontains [System.IO.Path]::GetExtension($_).ToLowerInvariant())
    }

    $allow = New-Object 'System.Collections.Generic.HashSet[string]'
    if (Test-Path $AllowListPath) {
        foreach ($line in Get-Content $AllowListPath) {
            $t = $line.Trim()
            if (-not $t -or $t.StartsWith('#')) { continue }
            $parts = $t -split '\|', 3
            if ($parts.Count -ge 2) {
                [void]$allow.Add(('{0}|{1}' -f $parts[0].Trim().ToLowerInvariant(), $parts[1].Trim().ToLowerInvariant()))
            }
        }
    }

    function Test-Allowed([string]$Path, [string]$Term) {
        $p = $Path.ToLowerInvariant()
        $t = $Term.ToLowerInvariant()
        return $allow.Contains("*|$t") -or $allow.Contains("$p|$t")
    }

    $findings = [System.Collections.Generic.List[object]]::new()
    $scanned = 0
    foreach ($file in $files) {
        $full = Join-Path $repoRoot $file
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
        $lines = $null
        try { $lines = Get-Content -LiteralPath $full -ErrorAction Stop }
        catch { continue }
        if ($null -eq $lines) { continue }
        $scanned++
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            foreach ($d in $denyTerms) {
                if ($line -imatch $d.Pattern) {
                    $trimmed = $line.Trim()
                    $findings.Add([pscustomobject]@{
                            Path    = $file
                            Line    = $i + 1
                            Term    = $d.Term
                            Text    = $trimmed.Substring(0, [Math]::Min(140, $trimmed.Length))
                            Allowed = (Test-Allowed $file $d.Term)
                        }) | Out-Null
                }
            }
        }
    }

    $enforced = @($findings | Where-Object { -not $_.Allowed })
    $suppressed = @($findings | Where-Object { $_.Allowed })

    Write-Host "scanned $scanned file(s) (excluding docs/platform-v2/**, AGENTS.md, tool self-reference, binaries)"
    Write-Host ''
    Write-Host 'by term:'
    $findings | Group-Object Term | Sort-Object Count -Descending | ForEach-Object {
        $allowedCount = @($_.Group | Where-Object Allowed).Count
        $suffix = if ($allowedCount) { " ($allowedCount allow-listed)" } else { '' }
        $fileCount = ($_.Group.Path | Select-Object -Unique).Count
        Write-Host ('  {0,-28} {1,4} hit(s) in {2,4} file(s){3}' -f $_.Name, $_.Count, $fileCount, $suffix)
    }
    Write-Host ''
    Write-Host "total: $($findings.Count) hit(s), $($enforced.Count) enforced, $($suppressed.Count) allow-listed"

    if ($Enforce -and $enforced.Count -gt 0) {
        Write-Host ''
        Write-Host 'ENFORCED FINDINGS (first 50):'
        $enforced | Select-Object -First 50 | ForEach-Object {
            Write-Host ('  {0}:{1}: [{2}] {3}' -f $_.Path, $_.Line, $_.Term, $_.Text)
        }
        exit 1
    }
    exit 0
}
finally {
    Pop-Location
}
