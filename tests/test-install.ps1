$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installer = Join-Path $repo "install.ps1"
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-dev-install-" + [guid]::NewGuid())
$passCount = 0

function Assert-Path([string]$Path) {
    if (-not (Test-Path $Path)) { throw "Missing path: $Path" }
}
function Assert-Absent([string]$Path) {
    if (Test-Path $Path) { throw "Unexpected path: $Path" }
}
function Pass([string]$Name) {
    $script:passCount++
    Write-Host "PASS: $Name"
}

try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null

    $fresh = Join-Path $testRoot "fresh config"
    & $installer -ConfigDir $fresh -Lang en | Out-Null
    Assert-Path (Join-Path $fresh "skills\dev\SKILL.md")
    Assert-Path (Join-Path $fresh "skills\dev\phases\external-review.md")
    Assert-Path (Join-Path $fresh "skills\dev\phases\phase5.md")
    Assert-Path (Join-Path $fresh "skills\dev\scripts\inspect_external_reviews.py")
    Assert-Path (Join-Path $fresh "skills\dev\scripts\detect_execution_backend.py")
    Assert-Path (Join-Path $fresh "skills\dev\backends\contract.md")
    Assert-Path (Join-Path $fresh "skills\dev\backends\claude-native.md")
    Assert-Path (Join-Path $fresh "skills\dev\backends\traycer.md")
    Assert-Path (Join-Path $fresh "skills\dev\agents\report-back.md")
    Assert-Path (Join-Path $fresh "skills\dev\agents\reviewer.md")
    Assert-Path (Join-Path $fresh "skills\dev\templates\DEV_STATE_TEMPLATE.md")
    Pass "fresh install with path spaces"

    $dry = Join-Path $testRoot "dry run"
    & $installer -ConfigDir $dry -DryRun | Out-Null
    Assert-Absent $dry
    Pass "dry run is non-mutating"

    $invalid = Join-Path $testRoot "invalid language"
    $rejected = $false
    try { & $installer -ConfigDir $invalid -Lang zh | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw "Chinese install unexpectedly succeeded" }
    Assert-Absent $invalid
    Pass "unsupported language rejected before mutation"

    $legacy = Join-Path $testRoot "legacy config"
    New-Item -ItemType Directory -Force -Path (Join-Path $legacy "commands\dev") | Out-Null
    Set-Content -Path (Join-Path $legacy "commands\dev.md") -Value "legacy entry"
    Set-Content -Path (Join-Path $legacy "commands\dev\phase.md") -Value "legacy phase"
    & $installer -ConfigDir $legacy | Out-Null
    Assert-Path (Join-Path $legacy "skills\dev\SKILL.md")
    Assert-Absent (Join-Path $legacy "commands\dev.md")
    Assert-Absent (Join-Path $legacy "commands\dev")
    $legacyBackup = Get-ChildItem (Join-Path $legacy "backups\dev") -Filter dev.md -File -Recurse | Select-Object -First 1
    if (-not $legacyBackup) { throw "Legacy backup missing" }
    Pass "legacy migration and backup"

    $rollback = Join-Path $testRoot "rollback config"
    New-Item -ItemType Directory -Force -Path (Join-Path $rollback "skills\dev") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $rollback "commands\dev") | Out-Null
    Set-Content -Path (Join-Path $rollback "skills\dev\old.txt") -Value "old skill"
    Set-Content -Path (Join-Path $rollback "commands\dev.md") -Value "legacy entry"
    Set-Content -Path (Join-Path $rollback "commands\dev\old-phase.md") -Value "legacy phase"
    $env:DEV_INSTALL_FAIL_AT = "after-backup"
    $failed = $false
    try { & $installer -ConfigDir $rollback | Out-Null } catch { $failed = $true }
    Remove-Item Env:DEV_INSTALL_FAIL_AT -ErrorAction SilentlyContinue
    if (-not $failed) { throw "Injected failure unexpectedly succeeded" }
    Assert-Path (Join-Path $rollback "skills\dev\old.txt")
    Assert-Path (Join-Path $rollback "commands\dev.md")
    Assert-Path (Join-Path $rollback "commands\dev\old-phase.md")
    Pass "rollback after backup"

    # Dirty checkout: uncommitted edits to tracked files and ignored/untracked
    # files under skills/dev must not ship (Issue #44).
    $dirtySource = Join-Path $testRoot "dirty-source"
    New-Item -ItemType Directory -Force -Path $dirtySource | Out-Null
    Copy-Item (Join-Path $repo "*") $dirtySource -Recurse -Force
    Add-Content -Path (Join-Path $dirtySource "skills\dev\SKILL.md") -Value "`n<!-- local edit: must not ship -->"
    New-Item -ItemType Directory -Force -Path (Join-Path $dirtySource "skills\dev\scripts\__pycache__") | Out-Null
    Set-Content -Path (Join-Path $dirtySource "skills\dev\scripts\__pycache__\x.pyc") -Value "compiled"
    $dirtyTarget = Join-Path $testRoot "dirty target"
    & (Join-Path $dirtySource "install.ps1") -ConfigDir $dirtyTarget -Lang en | Out-Null
    Assert-Path (Join-Path $dirtyTarget "skills\dev\SKILL.md")
    if (Select-String -Path (Join-Path $dirtyTarget "skills\dev\SKILL.md") -Pattern "local edit: must not ship" -Quiet) {
        throw "Uncommitted edit to a tracked file shipped in the install"
    }
    Assert-Absent (Join-Path $dirtyTarget "skills\dev\scripts\__pycache__")
    Pass "dirty checkout excludes uncommitted edits and ignored files"

    # No .git source: falls back to the working-tree copy and reports tarball
    # provenance instead of a commit (Issue #44, ADR-007 tarball/libexec case).
    $nogitSource = Join-Path $testRoot "nogit-source"
    New-Item -ItemType Directory -Force -Path $nogitSource | Out-Null
    Copy-Item (Join-Path $repo "*") $nogitSource -Recurse -Force
    Remove-Item (Join-Path $nogitSource ".git") -Recurse -Force -ErrorAction SilentlyContinue
    $nogitTarget = Join-Path $testRoot "nogit target"
    # 6>&1 merges the Information stream (what Write-Host writes to) into the
    # success stream so the provenance line below can be captured.
    $nogitOutput = & (Join-Path $nogitSource "install.ps1") -ConfigDir $nogitTarget -Lang en 6>&1
    Assert-Path (Join-Path $nogitTarget "skills\dev\SKILL.md")
    if (-not ($nogitOutput -match "Installed from: no git metadata \(tarball install\)")) {
        throw "No-.git install did not report tarball provenance"
    }
    Pass "no-.git source installs via the copy path with tarball provenance"

    # Clean checkout: the install reports the staged commit (Issue #44).
    $cleanTarget = Join-Path $testRoot "clean target"
    $cleanOutput = & $installer -ConfigDir $cleanTarget -Lang en 6>&1
    $expectedCommit = (& git -C $repo rev-parse HEAD).Trim()
    if (-not ($cleanOutput -match "Installed from commit $expectedCommit")) {
        throw "Clean checkout install did not report the staged commit"
    }
    Pass "clean checkout install reports commit provenance"

    Write-Host "All $passCount PowerShell installer tests passed."
}
finally {
    Remove-Item Env:DEV_INSTALL_FAIL_AT -ErrorAction SilentlyContinue
    if (Test-Path $testRoot) { Remove-Item $testRoot -Recurse -Force }
}
