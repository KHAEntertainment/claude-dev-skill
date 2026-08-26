# Install the English /dev personal Skill for Claude Code on Windows.
[CmdletBinding()]
param(
    [string]$Lang = "en",
    [string]$ConfigDir = $(if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".claude" }),
    [string]$Target,
    [switch]$MigrateLegacy,
    [switch]$KeepLegacy,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($Lang -ne "en") {
    throw "This maintained distribution is English-only; use -Lang en."
}
if ($MigrateLegacy -and $KeepLegacy) {
    throw "Choose either -MigrateLegacy or -KeepLegacy, not both."
}

$source = Join-Path $PSScriptRoot "skills\dev"
$validator = Join-Path $PSScriptRoot "scripts\validate_skill.py"
$targetWasExplicit = $PSBoundParameters.ContainsKey("Target")
if (-not $Target) {
    $Target = Join-Path $ConfigDir "skills\dev"
}
if ((Split-Path $Target -Leaf) -ne "dev") {
    throw "-Target must be the exact dev Skill directory and end in \dev: $Target"
}
$unsafeTargets = @([IO.Path]::GetPathRoot($Target), $env:USERPROFILE, $ConfigDir)
if ($unsafeTargets -contains $Target) {
    throw "Unsafe install target: $Target"
}
if (Test-Path $Target) {
    $targetItem = Get-Item $Target -Force
    if ($targetItem.LinkType) { throw "Refusing to replace symlink target: $Target" }
}

$pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $pythonCommand) { $pythonCommand = Get-Command python -ErrorAction SilentlyContinue }
if (-not $pythonCommand) { throw "Python 3 is required for validation." }
$pythonExe = $pythonCommand.Source
if (-not (Get-Command rtk -ErrorAction SilentlyContinue)) { throw "RTK is required by this customized /dev workflow." }
& $pythonExe $validator --skill-dir $source
if ($LASTEXITCODE -ne 0) { throw "Skill validation failed." }

$migrate = if ($MigrateLegacy) { $true } elseif ($KeepLegacy) { $false } else { -not $targetWasExplicit }
$legacyFile = Join-Path $ConfigDir "commands\dev.md"
$legacyDir = Join-Path $ConfigDir "commands\dev"
if ($migrate) {
    foreach ($legacyPath in @($legacyFile, $legacyDir)) {
        if (Test-Path $legacyPath) {
            $legacyItem = Get-Item $legacyPath -Force
            if ($legacyItem.LinkType) { throw "Refusing to migrate symlink path: $legacyPath" }
        }
    }
}

Write-Host "Source: $source"
Write-Host "Target: $Target"
Write-Host "Legacy migration: $migrate"
if ($DryRun) {
    Write-Host "DRY RUN: validation passed; no files changed."
    return
}

$targetParent = Split-Path $Target -Parent
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") + "-$PID"
$backup = Join-Path $ConfigDir "backups\dev\$stamp"
$stage = Join-Path $targetParent ".dev-stage-$stamp"
$hadTarget = $false
$hadLegacyFile = $false
$hadLegacyDir = $false
$installedNew = $false

try {
    New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
    New-Item -ItemType Directory -Path $stage | Out-Null
    Copy-Item (Join-Path $source "*") $stage -Recurse -Force
    & $pythonExe $validator --skill-dir $stage
    if ($LASTEXITCODE -ne 0) { throw "Staged Skill validation failed." }

    if ($env:DEV_INSTALL_FAIL_AT -eq "after-stage") { throw "Injected failure after stage." }

    if (Test-Path $Target) {
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        Move-Item $Target (Join-Path $backup "skill")
        $hadTarget = $true
    }

    if ($migrate -and ((Test-Path $legacyFile) -or (Test-Path $legacyDir))) {
        $legacyBackup = Join-Path $backup "legacy"
        New-Item -ItemType Directory -Force -Path $legacyBackup | Out-Null
        if (Test-Path $legacyFile) {
            Move-Item $legacyFile (Join-Path $legacyBackup "dev.md")
            $hadLegacyFile = $true
        }
        if (Test-Path $legacyDir) {
            Move-Item $legacyDir (Join-Path $legacyBackup "dev")
            $hadLegacyDir = $true
        }
    }

    if ($env:DEV_INSTALL_FAIL_AT -eq "after-backup") { throw "Injected failure after backup." }

    Move-Item $stage $Target
    $installedNew = $true
    if ($env:DEV_INSTALL_FAIL_AT -eq "after-install") { throw "Injected failure after install." }
}
catch {
    Write-Warning "Install failed; rolling back: $_"
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    if ($installedNew -and (Test-Path $Target)) { Remove-Item $Target -Recurse -Force }
    if ($hadTarget) { Move-Item (Join-Path $backup "skill") $Target }
    if ($hadLegacyFile) {
        New-Item -ItemType Directory -Force -Path (Split-Path $legacyFile -Parent) | Out-Null
        Move-Item (Join-Path $backup "legacy\dev.md") $legacyFile
    }
    if ($hadLegacyDir) {
        New-Item -ItemType Directory -Force -Path (Split-Path $legacyDir -Parent) | Out-Null
        Move-Item (Join-Path $backup "legacy\dev") $legacyDir
    }
    throw
}

Write-Host "Installed /dev Skill at $Target"
if (Test-Path $backup) { Write-Host "Previous files backed up at $backup" }
Write-Host "Restart Claude Code, then invoke /dev."
