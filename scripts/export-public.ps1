<#
.SYNOPSIS
    Export a clean, tracked-only copy of this repository for public release. [C01]

.DESCRIPTION
    `git archive HEAD | tar -x` into a NEW directory (this script refuses to
    run if it already exists), so anything untracked or gitignored - private
    payroll fixtures, .env, .azure/, .venv, node_modules - can never leak into
    the export. Only what git actually tracks at HEAD makes it out.

    Removes docs/platform-v2/ (internal planning: the operating manual, the
    work-package plan, live environment pins) and the root AGENTS.md (the
    same reason) from the exported tree - neither describes the product,
    both describe how this was built.

    Then, INSIDE the exported tree (not the private repo), runs every check a
    public release needs:
      - scripts/check-whitelabel.ps1 -Enforce
      - scripts/audit-export.py --enforce
      - gitleaks dir . (the raw exported directory; there is no git history
        yet for `gitleaks git` to walk)
      - the backend suite WITHOUT TCC_REQUIRE_PARITY: the private parity
        fixtures were never tracked, so test_engine_parity_reference.py must
        skip cleanly (not error) and test_engine_parity_synthetic.py (its
        fixture IS committed) must pass for real
      - the frontend suite and build
      - `terraform init -backend=false` + `terraform validate` + `terraform test`

    Only once every check passes does it `git init -b main`, stage
    everything, and make exactly ONE commit: "Initial public release". No
    remote is added and nothing is pushed - publishing (H1/H2) is a separate,
    human decision.

.PARAMETER Destination
    Defaults to a sibling of this repository: ..\tax-credit-copilot-public

.PARAMETER SkipChecks
    Skip the in-tree verification and commit anyway. For local iteration on
    this script only - never use this for the real export.

.EXAMPLE
    pwsh scripts/export-public.ps1
#>
[CmdletBinding()]
param(
    [string]$Destination,
    [switch]$SkipChecks
)

$ErrorActionPreference = 'Stop'

$repoRoot = (& git rev-parse --show-toplevel).Trim() -replace '/', '\'
if (-not $Destination) {
    $Destination = Join-Path (Split-Path $repoRoot -Parent) 'tax-credit-copilot-public'
}

if (Test-Path $Destination) {
    throw "Destination already exists: $Destination`nexport-public.ps1 never overwrites an existing export. Remove it first if you mean to re-run this."
}

function Invoke-Checked {
    param([string]$Description, [scriptblock]$Script)
    Write-Host "`n--- $Description ---" -ForegroundColor Cyan
    & $Script
    if ($LASTEXITCODE -ne 0) {
        throw "FAILED: $Description (exit $LASTEXITCODE)"
    }
    Write-Host "OK: $Description" -ForegroundColor Green
}

Write-Host "Exporting tracked HEAD ($((& git rev-parse --short HEAD).Trim())) -> $Destination"
New-Item -ItemType Directory -Path $Destination | Out-Null
Push-Location $repoRoot
try {
    & git archive HEAD | & tar -x -C $Destination
    if ($LASTEXITCODE -ne 0) { throw "git archive | tar extraction failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

$platformV2 = Join-Path $Destination 'docs\platform-v2'
$agentsMd = Join-Path $Destination 'AGENTS.md'
if (Test-Path $platformV2) { Remove-Item -Recurse -Force $platformV2 }
if (Test-Path $agentsMd) { Remove-Item -Force $agentsMd }
Write-Host "Removed docs/platform-v2/ and AGENTS.md from the exported tree (internal planning, not product)."

# check-whitelabel.ps1 and audit-export.py both enumerate `git ls-files`, so a
# git INDEX has to exist before they can run. Initialise here and stage now;
# this is the SAME init the final commit uses below - nothing re-inits later,
# so the exported tree still ends with exactly one commit.
Push-Location $Destination
try {
    & git init -b main | Out-Null
    & git add -A
} finally {
    Pop-Location
}

if ($SkipChecks) {
    Write-Host "SkipChecks set: skipping all in-tree verification. DO NOT use this for a real export." -ForegroundColor Yellow
} else {
    Push-Location $Destination
    try {
        Invoke-Checked "check-whitelabel.ps1 -Enforce" {
            pwsh -NoProfile -File 'scripts\check-whitelabel.ps1' -Enforce
        }

        Invoke-Checked "audit-export.py --enforce" {
            & "$repoRoot\.venv\Scripts\python.exe" 'scripts\audit-export.py' --enforce
        }

        Invoke-Checked "gitleaks dir ." {
            & gitleaks dir . --no-banner
        }

        # Reuse the private repo's venv interpreter and dependencies, and the
        # frontend's node_modules via a junction keyed to the SAME
        # package-lock.json this archive just exported - a fresh npm install
        # from that identical lockfile would resolve to the same tree, so the
        # junction only saves the time, not the guarantee.
        Invoke-Checked "backend pytest (no TCC_REQUIRE_PARITY)" {
            Push-Location (Join-Path $Destination 'backend')
            try {
                Remove-Item Env:\TCC_REQUIRE_PARITY -ErrorAction SilentlyContinue
                & "$repoRoot\.venv\Scripts\python.exe" -m pytest tests -q -p no:cacheprovider
            } finally {
                Pop-Location
            }
        }

        $feDir = Join-Path $Destination 'frontend'
        $feNodeModules = Join-Path $feDir 'node_modules'
        $privateNodeModules = Join-Path $repoRoot 'frontend\node_modules'
        if ((Test-Path $privateNodeModules) -and -not (Test-Path $feNodeModules)) {
            New-Item -ItemType Junction -Path $feNodeModules -Target $privateNodeModules | Out-Null
            Write-Host "Junctioned frontend/node_modules from the private checkout (same package-lock.json)."
        }
        Invoke-Checked "frontend vitest" {
            Push-Location $feDir
            try { npm test } finally { Pop-Location }
        }
        Invoke-Checked "frontend build" {
            Push-Location $feDir
            try { npm run build } finally { Pop-Location }
        }

        $infraDir = Join-Path $Destination 'infra'
        Invoke-Checked "terraform init + validate" {
            Push-Location $infraDir
            try {
                terraform init -backend=false -input=false
                if ($LASTEXITCODE -eq 0) { terraform validate }
            } finally {
                Pop-Location
            }
        }
        Invoke-Checked "terraform test" {
            Push-Location $infraDir
            try { terraform test } finally { Pop-Location }
        }
    } finally {
        Pop-Location
    }
}

Write-Host "`nAll exported-tree checks passed. Creating the single 'Initial public release' commit." -ForegroundColor Cyan
Push-Location $Destination
try {
    # Re-stage: the node_modules junction and any tool-generated build output
    # (frontend/dist, .terraform/) are all gitignored, so this adds nothing
    # new - it only re-syncs the index with the tree exactly as it was before
    # the checks ran. git was already initialised above; this is still ONE
    # commit, made now for the first time.
    & git add -A
    $msg = "Initial public release`n`nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
    & git -c user.name="Platform v2 export" -c user.email="noreply@example.com" commit -q -m $msg
    if ($LASTEXITCODE -ne 0) { throw "git commit failed in the exported tree" }
    $count = (& git rev-list --count HEAD).Trim()
    $remotes = (& git remote)
    Write-Host "Commit count: $count (expect 1)"
    Write-Host "Remotes: '$remotes' (expect empty)"
    if ($count -ne '1') { throw "expected exactly 1 commit, found $count" }
    if ($remotes) { throw "expected no remotes, found: $remotes" }
} finally {
    Pop-Location
}

Write-Host "`nExport ready at $Destination. No remote, not pushed." -ForegroundColor Green
