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

    Write-Host "All $passCount PowerShell installer tests passed."
}
finally {
    Remove-Item Env:DEV_INSTALL_FAIL_AT -ErrorAction SilentlyContinue
    if (Test-Path $testRoot) { Remove-Item $testRoot -Recurse -Force }
}
